# Local model delegation

The project can use Barbara's LM Studio model for subprocess and review tasks.

- **Host:** `barbara`
- **Base URL:** `http://barbara:1234/v1`
- **Model:** `nvidia/nemotron-3-nano-4b`
- **Chat endpoint:** `http://barbara:1234/v1/chat/completions`
- **Helper:** `./requi_assistant.py`

## Usage

From this directory:

```sh
./requi_assistant.py "Find missing glossary back-links"
./requi_assistant.py "Propose the next requirements for this project"
```

The helper sends the readable Markdown files in this project as context. It is read-only: the model proposes answers and changes but does not edit project files.

Override the defaults when needed:

```sh
LM_STUDIO_URL=http://barbara:1234/v1 \
LM_MODEL=nvidia/nemotron-3-nano-4b \
./requi_assistant.py "Review the requirements"
```

Before applying model output, verify every referenced file, requirement ID, term, and cross-link against the repository. The model may produce incorrect or invented paths.
