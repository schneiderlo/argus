import json
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
    
    if run_id is None or run_id == "latest":
        runs = store.list_runs()
        if not runs:
            print("No runs found to observe.")
            return
        runs.sort(key=lambda r: r.updated_at, reverse=True)
        run_id = runs[0].run_id

    print(f"Starting Argus observer on http://localhost:{port} for run: {run_id}")
    
    class ObserverHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            parsed_path = parsed.path
            parsed_query = parse_qs(parsed.query)

            if parsed_path == "/":
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                
                html_path = Path(__file__).parent / "render" / "observer.html"
                if html_path.exists():
                    self.wfile.write(html_path.read_bytes())
                else:
                    self.wfile.write(b"<html><body>Observer HTML not found.</body></html>")
                
            elif parsed_path == "/api/events":
                try:
                    limit = _parse_events_limit(parsed_query)
                except ValueError as exc:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
                    return
                try:
                    events = store.load_progress_events(run_id, limit=limit)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(events).encode("utf-8"))
                except Exception as exc:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
            elif parsed_path == "/api/state":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                
                try:
                    persisted_run = store.load_run(run_id)
                    state = persisted_run.state
                    if state:
                        data = state.to_dict()
                        data["nodes"] = _annotate_nodes_with_termination_reason(data.get("nodes"))
                        data["manifest"] = persisted_run.manifest.to_dict()
                        self.wfile.write(json.dumps(data).encode("utf-8"))
                    else:
                        self.wfile.write(b"{}")
                except Exception as e:
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

            return

        def do_POST(self):
            if self.path == "/api/prune":
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                payload = json.loads(post_data)
                node_id_to_prune = payload.get("node_id")

                try:
                    persisted_run = store.load_run(run_id)
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
                            run_id,
                            state=new_state,
                            status=persisted_run.manifest.status
                        )
                        
                        self.send_response(200)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
                    else:
                        self.send_response(404)
                        self.end_headers()
                        self.wfile.write(b'{"error": "Node not found"}')
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # Suppress default HTTP server logging to keep terminal clean
            pass

    server_address = ('', port)
    httpd = HTTPServer(server_address, ObserverHandler)
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
