import { app } from "/scripts/app.js";

app.registerExtension({
  name: "MiniMax.H3.30s",
  async setup() {
    const key = "minimax-h3-30s-initial-workflow-v1";
    if (localStorage.getItem(key)) return;
    setTimeout(async () => {
      try {
        const response = await fetch("/extensions/h3_30s_app/workflow.json");
        if (!response.ok) return;
        await app.loadGraphData(await response.json());
        localStorage.setItem(key, "loaded");
      } catch (error) {
        console.warn("30s workflow can be opened from the workflows menu", error);
      }
    }, 1500);
  },
});
