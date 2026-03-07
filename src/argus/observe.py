import json
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dataclasses import replace
from collections.abc import Mapping
from urllib.parse import parse_qs, urlparse

from argus.config import ArgusConfig
from argus.storage import FileSystemStateStore
from argus.models import NodeLifecycleStatus


def _node_termination_reason(node_payload: Mapping[str, object]) -> str | None:
    lifecycle_status = node_payload.get("lifecycle_status")
    metadata = node_payload.get("metadata")
    metadata_dict = metadata if isinstance(metadata, Mapping) else {}

    if lifecycle_status == NodeLifecycleStatus.REJECTED.value:
        novelty = metadata_dict.get("novelty")
        novelty_dict = novelty if isinstance(novelty, Mapping) else {}
        summary = novelty_dict.get("summary")
        if isinstance(summary, str) and summary.strip():
            return f"Rejected by novelty gate: {summary.strip()}"

        nearest = novelty_dict.get("nearest_neighbor_id")
        max_similarity = novelty_dict.get("max_similarity")
        if isinstance(nearest, str) and nearest.strip() and isinstance(max_similarity, (int, float)):
            return (
                "Rejected by novelty gate due to near-duplicate overlap with "
                f"{nearest.strip()} (similarity {float(max_similarity):.2f})."
            )
        return "Rejected by novelty gate because the candidate was too similar to an archived node."

    if lifecycle_status == NodeLifecycleStatus.FAILED.value:
        score = node_payload.get("score")
        score_dict = score if isinstance(score, Mapping) else {}
        hard_constraint_reasons = score_dict.get("hard_constraint_reasons")
        if isinstance(hard_constraint_reasons, list):
            normalized_reasons = [
                reason.strip()
                for reason in hard_constraint_reasons
                if isinstance(reason, str) and reason.strip()
            ]
            if normalized_reasons:
                return "Failed hard constraints: " + "; ".join(normalized_reasons)
        return "Failed hard-constraint gate."

    if lifecycle_status == NodeLifecycleStatus.PRUNED.value:
        return "Terminated manually by operator."

    return None


def _annotate_nodes_with_termination_reason(nodes_payload: object) -> object:
    if not isinstance(nodes_payload, Mapping):
        return nodes_payload

    annotated: dict[str, object] = {}
    for node_id, node_payload in nodes_payload.items():
        if not isinstance(node_payload, Mapping):
            annotated[str(node_id)] = node_payload
            continue
        normalized_node_payload = dict(node_payload)
        reason = _node_termination_reason(normalized_node_payload)
        if reason is not None:
            normalized_node_payload["termination_reason"] = reason
        annotated[str(node_id)] = normalized_node_payload
    return annotated


def start_observer_server(config: ArgusConfig, run_id: str | None, port: int):
    store = FileSystemStateStore(config.runs_dir)
    
    default_run_id = run_id
    if default_run_id is None or default_run_id == "latest":
        runs = store.list_runs()
        if runs:
            runs.sort(key=lambda r: r.updated_at, reverse=True)
            default_run_id = runs[0].run_id

    if default_run_id:
        print(f"Default run: {default_run_id}")
    
    class ObserverHandler(BaseHTTPRequestHandler):
        def _send_json(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        def _send_error(self, message, status=500):
            self._send_json({"error": message}, status)

        def do_GET(self):
            parsed = urlparse(self.path)
            parsed_path = parsed.path
            parsed_query = parse_qs(parsed.query)

            if parsed_path.startswith("/api/"):
                try:
                    parts = [p for p in parsed_path.split("/") if p]
                    
                    if len(parts) == 2 and parts[1] == "runs":
                        runs = store.list_runs()
                        runs.sort(key=lambda r: r.updated_at, reverse=True)
                        self._send_json([r.to_dict() for r in runs])
                        return
                    
                    if len(parts) == 2 and parts[1] == "default-run":
                        if default_run_id:
                            self._send_json({"run_id": default_run_id})
                        else:
                            self._send_error("No default run", 404)
                        return
                        
                    if len(parts) == 2 and parts[1] == "memory":
                        self._send_json({
                            "learning_memory": store.load_learning_memory().to_dict(),
                            "routing_stats": store.load_provider_routing_stats().to_dict(),
                        })
                        return

                    if len(parts) == 4 and parts[1] == "runs" and parts[3] == "state":
                        target_run_id = parts[2]
                        persisted_run = store.load_run(target_run_id)
                        state = persisted_run.state
                        if state:
                            data = state.to_dict()
                            data["nodes"] = _annotate_nodes_with_termination_reason(data.get("nodes"))
                            data["manifest"] = persisted_run.manifest.to_dict()
                            self._send_json(data)
                        else:
                            self._send_json({})
                        return

                    if len(parts) == 4 and parts[1] == "runs" and parts[3] == "events":
                        target_run_id = parts[2]
                        limit = _parse_events_limit(parsed_query)
                        events = store.load_progress_events(target_run_id, limit=limit)
                        self._send_json(events)
                        return

                    if parsed_path == "/api/state" and default_run_id:
                        persisted_run = store.load_run(default_run_id)
                        state = persisted_run.state
                        if state:
                            data = state.to_dict()
                            data["nodes"] = _annotate_nodes_with_termination_reason(data.get("nodes"))
                            data["manifest"] = persisted_run.manifest.to_dict()
                            self._send_json(data)
                        else:
                            self._send_json({})
                        return
                        
                    if parsed_path == "/api/events" and default_run_id:
                        limit = _parse_events_limit(parsed_query)
                        events = store.load_progress_events(default_run_id, limit=limit)
                        self._send_json(events)
                        return

                    self._send_error("Not found", 404)
                except Exception as exc:
                    self._send_error(str(exc), 500)
                return

            dist_path = Path(__file__).parent / "render" / "dist"
            if not dist_path.exists():
                html_path = Path(__file__).parent / "render" / "observer.html"
                if html_path.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(html_path.read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"UI dist folder not found.")
                return

            file_path = dist_path / parsed_path.lstrip("/")
            try:
                file_path = file_path.resolve()
                if not str(file_path).startswith(str(dist_path.resolve())):
                    self.send_response(403)
                    self.end_headers()
                    return
            except Exception:
                pass

            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                ext = file_path.suffix.lower()
                mime = "application/octet-stream"
                if ext == ".html":
                    mime = "text/html"
                elif ext == ".js":
                    mime = "application/javascript"
                elif ext == ".css":
                    mime = "text/css"
                elif ext == ".json":
                    mime = "application/json"
                elif ext == ".svg":
                    mime = "image/svg+xml"
                elif ext == ".png":
                    mime = "image/png"
                elif ext == ".ico":
                    mime = "image/x-icon"
                
                self.send_header("Content-type", mime)
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
            else:
                index_path = dist_path / "index.html"
                if index_path.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(index_path.read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()
            return

        def do_POST(self):
            parsed = urlparse(self.path)
            parsed_path = parsed.path
            
            if parsed_path.startswith("/api/"):
                try:
                    parts = [p for p in parsed_path.split("/") if p]
                    
                    target_run_id = default_run_id
                    if len(parts) == 4 and parts[1] == "runs" and parts[3] == "prune":
                        target_run_id = parts[2]
                    elif parsed_path != "/api/prune":
                        self._send_error("Not found", 404)
                        return
                        
                    if not target_run_id:
                        self._send_error("No run specified", 400)
                        return

                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data)
                    node_id_to_prune = payload.get("node_id")

                    persisted_run = store.load_run(target_run_id)
                    state = persisted_run.state
                    if state and node_id_to_prune in state.nodes:
                        node = state.nodes[node_id_to_prune]
                        new_node = replace(node, lifecycle_status=NodeLifecycleStatus.PRUNED)
                        
                        new_frontier = [n for n in state.frontier_ids if n != node_id_to_prune]
                        new_archive = [n for n in state.archive_ids if n != node_id_to_prune]
                        new_pruned = list(state.pruned_ids)
                        if node_id_to_prune not in new_pruned:
                            new_pruned.append(node_id_to_prune)
                        
                        new_nodes = dict(state.nodes)
                        new_nodes[node_id_to_prune] = new_node
                        
                        new_islands = dict(state.islands)
                        if node.island_id and node.island_id in new_islands:
                            island = new_islands[node.island_id]
                            new_island_frontier = [n for n in island.frontier_ids if n != node_id_to_prune]
                            new_island_archive = [n for n in island.archive_ids if n != node_id_to_prune]
                            new_island_pruned = list(island.pruned_ids)
                            if node_id_to_prune not in new_island_pruned:
                                new_island_pruned.append(node_id_to_prune)
                            new_islands[node.island_id] = replace(
                                island,
                                archive_ids=new_island_archive,
                                frontier_ids=new_island_frontier,
                                pruned_ids=new_island_pruned
                            )
                        
                        new_state = replace(
                            state,
                            nodes=new_nodes,
                            archive_ids=new_archive,
                            frontier_ids=new_frontier,
                            pruned_ids=new_pruned,
                            islands=new_islands
                        )
                        
                        store.save_snapshot(
                            target_run_id,
                            state=new_state,
                            status=persisted_run.manifest.status
                        )
                        
                        self._send_json({"status": "success"})
                    else:
                        self._send_error("Node not found", 404)
                except Exception as e:
                    self._send_error(str(e), 500)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    httpd = None
    for attempt_port in range(port, port + 10):
        try:
            server_address = ('', attempt_port)
            httpd = HTTPServer(server_address, ObserverHandler)
            port = attempt_port
            break
        except OSError as e:
            if e.errno == 98: # Address already in use
                continue
            raise

    if httpd is None:
        print(f"Failed to bind to any port from {port} to {port + 9}", file=sys.stderr)
        return

    print(f"Starting Argus Command Center on http://localhost:{port}")
    try:
        webbrowser.open(f'http://localhost:{port}')
    except Exception:
        pass
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()


def _parse_events_limit(query: Mapping[str, list[str]]) -> int | None:
    raw_values = query.get("limit")
    if not raw_values:
        return None
    try:
        value = int(raw_values[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a non-negative integer") from exc
    if value < 0:
        raise ValueError("limit must be zero or greater")
    return value
