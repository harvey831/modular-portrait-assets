# CC0 release audit

Audit date: 2026-09-01 (Asia/Hong_Kong)

## Result

The clean export passed its technical publication gate:

- 974 hash-bound current-authority assets;
- 172,106,675 total asset bytes;
- 540 PNG and 434 WebP files;
- every asset decodes as 1254×1254 RGBA;
- zero asset paths containing RMBG, `_work_history`, `old_versions`,
  `candidates`, `tmp`, or `qc`;
- zero model-weight files (`safetensors`, `ckpt`, `pth`, `pt`, `onnx`, or
  `bin`);
- zero unexpected assets outside the public SHA-256 manifest.

The accepted commercial-removal v03 production record identifies 30 affected
modules as freshly rebuilt with InSPyReNet and promoted on 2026-09-01. Only the
promoted bytes are present here; the old removal masks and historical evidence
remain private.

## Authority binding

- Female authority SHA-256:
  `e78e429b3baf4c8e50400bce6daf5b2124b96d840594689a355ee0747fcea679`
- Male authority SHA-256:
  `0df43834582bbbcbb2ef09d420fbb340824f6e9a535200eea40145cf00c71ad2`

These hashes identify the private selection records used for this export. The
public asset manifest independently binds every released file.

## Rights conclusion

The technical audit establishes what is included and proves that the release
does not contain the known historical or third-party packages. CC0 is applied
by the repository rights holder to the extent they own the exported work. It
does not waive rights belonging to other people and is not a guarantee that AI
output is unique.

Before the first public push, the repository owner should confirm that all
locked generation inputs were project-owned or otherwise authorized for this
dedication. Any later contribution must pass the same rights and hash gate.
