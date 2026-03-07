Design a highly optimized, compute-shader-driven WebGPU engine architecture for a massive multiplayer voxel game

**The constraints:** 
1. It must render a 2km x 2km world with 0.25m³ voxel precision entirely via raycasted compute shaders without using traditional rasterization, maintaining a locked 60+ FPS on mid-range integrated GPUs (like an Apple M1).
2. The initial world state (an 8192x8192 16-bit heightmap or sparse voxel octree) must be losslessly compressed to under 40MB for fast browser loading over the web.
3. It must support 10,000 concurrent players terraforming the world continuously in real-time.

Recommend the most efficient end-to-end technical strategy.