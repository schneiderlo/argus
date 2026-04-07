<script lang="ts">
  import { onMount } from 'svelte';
  import { Network } from 'vis-network';
  import type { Edge, Node, Options } from 'vis-network';
  import { DataSet } from 'vis-data';
  import { uiState, getStyle } from '$lib/stores.svelte';
  import type { SearchStatePayload } from '$lib/types';
  import { deriveGraphPresentation } from '$lib/components/networkGraphModel.js';

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
                  nodeSpacing: 180,
                  levelSeparation: 430
              }
          },
          physics: false,
          nodes: {
              shape: 'box',
              margin: { top: 10, bottom: 10, left: 16, right: 16 },
              borderWidth: 1.5,
              shapeProperties: { borderRadius: 8 },
              widthConstraint: { maximum: 250 },
              font: {
                  multi: 'html',
                  face: "'Geist Mono', monospace",
                  size: 12,
                  color: textColor,
                  align: 'center',
                  bold: {
                      color: textColor,
                      size: 12,
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
      const presentation = deriveGraphPresentation(state, {
          isLightMode: uiState.isLightMode,
          getStyle,
      });
      syncDataSet(nodes, presentation.nodes as Node[]);
      syncDataSet(edges, presentation.edges as Edge[]);
  }

  function syncDataSet(
      dataSet: DataSet<Node | Edge, 'id'>,
      items: Array<Node | Edge>
  ) {
      const nextIds = new Set(items.map((item) => String(item.id)));
      const staleIds = dataSet
          .getIds()
          .map((item) => String(item))
          .filter((item) => !nextIds.has(item));

      if (staleIds.length > 0) {
          dataSet.remove(staleIds);
      }
      dataSet.update(items);
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
