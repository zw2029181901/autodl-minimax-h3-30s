# Sources and notices

This independent application contains a 30-second workflow adaptation and deployment code. The existing 15-second application is preserved separately.

- ComfyUI: https://github.com/Comfy-Org/ComfyUI/tree/7c4390a6f70cd8eb41014d6af52969397a752fc4 — GPL-3.0.
- T8 long-video nodes and upstream workflow: https://github.com/T8mars/comfyui-minimax-h3-audio-T8/tree/ee569dab831cf0d14bf8578215c7250874fad2f6 — GPL-3.0-or-later. The workflow removes the upstream Turbo LoRA, selects native 20-step sampling and the pruned FL2VA INT8 model, adds Chinese usage notes and has its own workflow identifier.
- MiniMax H3: https://huggingface.co/MiniMaxAI/MiniMax-H3 — MiniMax H3 Community License.
- Qwen3-VL-32B: https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct — Apache-2.0. Standard license text: https://www.apache.org/licenses/LICENSE-2.0.txt.
- Converted models: https://huggingface.co/Comfy-Org/MiniMax-H3/tree/54472221d27c695fca9621b0c3ed52f06c4af707. Pinned filenames, sizes and SHA256 values are in sources.json. ModelScope transport revisions were checked against the same sizes and hashes.

The saved image contains the complete pinned ComfyUI and T8 source trees and their license notices. Its bundled Python environment retains third-party distribution notices. Model weights are prepared on the separate data disk.
