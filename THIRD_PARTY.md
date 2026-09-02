# Third-party components

- `tla/tla2tools.jar`: TLA+ Tools 2.0 (build 2024-08-08), from github.com/tlaplus/tlaplus, MIT License. Vendored so `make`-free reproduction of the TLC checks does not depend on a download; the licence text is inside the jar at `META-INF/`.
- The soft judge and the decision model run through a local Ollama server (`qwen2.5-coder:14b`, Apache 2.0 weights); nothing from the model is redistributed here.
