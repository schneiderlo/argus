import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dataclasses import replace

from argus.config import ArgusConfig
from argus.storage import FileSystemStateStore
from argus.models import NodeLifecycleStatus

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
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                
                html_path = Path(__file__).parent / "render" / "observer.html"
                if html_path.exists():
                    self.wfile.write(html_path.read_bytes())
                else:
                    self.wfile.write(b"<html><body>Observer HTML not found.</body></html>")
                
            elif self.path == "/api/state":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                
                try:
                    persisted_run = store.load_run(run_id)
                    state = persisted_run.state
                    if state:
                        data = state.to_dict()
                        data["manifest"] = persisted_run.manifest.to_dict()
                        self.wfile.write(json.dumps(data).encode("utf-8"))
                    else:
                        self.wfile.write(b"{}")
                except Exception as e:
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

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
                        new_pruned = list(set(state.pruned_ids) | {node_id_to_prune})
                        
                        new_nodes = dict(state.nodes)
                        new_nodes[node_id_to_prune] = new_node
                        
                        new_islands = dict(state.islands)
                        if node.island_id and node.island_id in new_islands:
                            island = new_islands[node.island_id]
                            new_island_frontier = [n for n in island.frontier_ids if n != node_id_to_prune]
                            new_island_pruned = list(set(island.pruned_ids) | {node_id_to_prune})
                            new_islands[node.island_id] = replace(
                                island,
                                frontier_ids=new_island_frontier,
                                pruned_ids=new_island_pruned
                            )
                        
                        new_state = replace(
                            state,
                            nodes=new_nodes,
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
