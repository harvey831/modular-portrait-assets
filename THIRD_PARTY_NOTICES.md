# Third-party notices

No third-party source code, model weights, custom-node package, or vendor
submodule is bundled in this repository.

The private production workflow used the following external tools. Their
licenses apply to those tools themselves, not as a replacement for this
repository's CC0 dedication:

- **InSPyReNet**, copyright Taehun Kim, MIT License. Used as a foreground-mask
  tool. Model/code files are not redistributed here.
- **ComfyUI VNCCS custom node**, MIT License. Used to invoke the selected
  foreground-removal route. The node is not redistributed here.
- **OpenAI image-generation services**. Generated/edited donors were obtained
  under the account holder's applicable OpenAI terms. OpenAI services and model
  files are not redistributed here.
- **Pillow**, MIT-CMU License. It is an external validation dependency declared
  in `requirements.txt`; Pillow source or binaries are not redistributed here.

The historical private library contains an `mspaintlib` MIT submodule. It is
excluded from this public package and no code from it is copied here.
