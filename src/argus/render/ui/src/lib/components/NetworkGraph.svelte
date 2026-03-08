<script lang="ts">
  import { onMount } from 'svelte';
  import { Network } from 'vis-network';
  import type { Edge, Node, Options } from 'vis-network';
  import { DataSet } from 'vis-data';
  import { uiState, getStyle } from '$lib/stores.svelte';
  import type { SearchStatePayload } from '$lib/types';

  let container: HTMLElement;
  let network: Network;
  let nodes = new DataSet<Node, 'id'>();
  let edges = new DataSet<Edge, 'id'>();

  function getVisOptions(): Options {
      const textColor = uiState.isLightMode ? '#18181b' : '#fafafa';
      const shadowColor = uiState.isLightMode ? 'rgba(0,0,0,0.15)' : 'rgba(0,0,0,0.6)';
      const edgeColor = uiState.isLightMode ? 'rgba(0, 0, 0, 0.15)' : 'rgba(255, 255, 255, 0.15)';
      const highlightColor = uiState.isLightMode ? '#2563eb' : '#60a5fa';

      return {
          layout: {
              hierarchical: {
                  direction: 'LR',
                  sortMethod: 'hubsize',
                  nodeSpacing: 140,
                  levelSeparation: 360
              }
          },
          physics: false,
          nodes: {
              shape: 'box',
              margin: { top: 14, bottom: 14, left: 20, right: 20 },
              borderWidth: 1.5,
              shapeProperties: { borderRadius: 8 },
              font: {
                  multi: 'html',
                  face: "'Geist Mono', monospace",
                  size: 13,
                  color: textColor,
                  align: 'center',
                  bold: {
                      color: textColor,
                      size: 13,
                      vadjust: 0
                  }
              },
              shadow: {
                  enabled: true,
                  color: shadowColor,
                  size: 15,
                  x: 0,
                  y: 6
              }
          },
          edges: {
              arrows: { to: { enabled: true, scaleFactor: 0.8 } },
              color: {
                  color: edgeColor,
                  highlight: highlightColor,
                  hover: highlightColor
              },
              width: 2,
              smooth: {
                  enabled: true,
                  type: 'cubicBezier',
                  forceDirection: 'horizontal',
                  roundness: 0.6
              }
          },
          interaction: {
              hover: true,
              tooltipDelay: 200,
              zoomView: true
          },
          autoResize: false
      };
  }

  onMount(() => {
      network = new Network(container, { nodes, edges }, getVisOptions());
      network.on("selectNode", (params) => {
          if (params.nodes.length > 0) {
              uiState.selectedNodeId = params.nodes[0];
          }
      });
      network.on("deselectNode", () => {
          uiState.selectedNodeId = null;
      });

      // Handle resize manually to avoid scaling/flicker
      const ro = new ResizeObserver(() => {
          if (network && container) {
              network.setSize(`${container.clientWidth}px`, `${container.clientHeight}px`);
              network.redraw();
          }
      });
      ro.observe(container);

      return () => {
          ro.disconnect();
          network?.destroy();
      };
  });

  // Effect to update theme options dynamically
  $effect(() => {
    if (network) {
        // Just reading `isLightMode` registers it as a dependency
        const currentMode = uiState.isLightMode;
        network.setOptions(getVisOptions());
        // Trigger a re-render of nodes with updated color palettes
        if (uiState.searchState) {
          syncGraphData(uiState.searchState);
        }
    }
  });

  // Effect to update graph data when state changes
  $effect(() => {
      if (uiState.searchState && network) {
          syncGraphData(uiState.searchState);
      }
  });

  function syncGraphData(state: SearchStatePayload) {
      if (!state.nodes) return;

      const visNodes: Node[] = [];
      const visEdges: Edge[] = [];
      const childToParents: Record<string, string[]> = {};

      for (const nodeId in state.nodes) {
          const node = state.nodes[nodeId];
          if (node.parent_ids && node.parent_ids.length > 0) {
              childToParents[nodeId] = node.parent_ids;
              for (const parentId of node.parent_ids) {
                  visEdges.push({
                      id: `${parentId}-${nodeId}`,
                      from: parentId,
                      to: nodeId,
                      color: { opacity: (node.lifecycle_status === 'pruned' || node.lifecycle_status === 'rejected') ? 0.2 : 0.8 },
                      dashes: (node.lifecycle_status === 'pruned' || node.lifecycle_status === 'rejected') ? [4, 4] : false
                  });
              }
          } else {
              childToParents[nodeId] = [];
          }
      }

      const nodeLevels: Record<string, number> = {};
      function getLevel(id: string): number {
          if (nodeLevels[id] !== undefined) return nodeLevels[id];
          const parents = childToParents[id] || [];
          if (parents.length === 0) {
              nodeLevels[id] = 0;
              return 0;
          }
          let maxParentLevel = -1;
          for (const pid of parents) {
              if (nodeLevels[pid] === undefined) {
                  nodeLevels[pid] = 0;
                  nodeLevels[pid] = getLevel(pid);
              }
              if (nodeLevels[pid] > maxParentLevel) {
                  maxParentLevel = nodeLevels[pid];
              }
          }
          nodeLevels[id] = maxParentLevel + 1;
          return nodeLevels[id];
      }

      for (const nodeId in state.nodes) {
          const node = state.nodes[nodeId];
          const status = node.lifecycle_status;
          const style = getStyle(status);

          let labelText = `<b>${node.action_type.toUpperCase()}</b>\n${nodeId}`;
          if (node.score && node.score.total_score !== undefined) {
              labelText += `\n★ ${node.score.total_score.toFixed(2)}`;
          }

          const nodeConfig: Node = {
              id: nodeId,
              level: getLevel(nodeId),
              label: labelText,
              color: {
                  background: style.bg,
                  border: style.border,
                  highlight: { background: style.bg, border: uiState.isLightMode ? '#000' : '#fff' },
                  hover: { background: style.bg, border: uiState.isLightMode ? '#000' : '#fff' }
              },
              font: { multi: 'html', color: style.text }
          };

          if (status === 'pruned' || status === 'rejected') {
              nodeConfig.shapeProperties = { borderDashes: [4, 4] };
              nodeConfig.font = {
                  ...(typeof nodeConfig.font === 'object' ? nodeConfig.font : {}),
                  color: uiState.isLightMode ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.4)',
              };
          }

          visNodes.push(nodeConfig);
      }

      // Instead of clear/add, update efficiently using vis-data
      // We only want to add new items or update changed ones to avoid resetting physics/positions 
      nodes.update(visNodes);
      edges.update(visEdges);
  }
</script>

<div bind:this={container} id="network-container"></div>

<style>
  #network-container {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 1;
      background: transparent;
      outline: none;
  }
</style>
