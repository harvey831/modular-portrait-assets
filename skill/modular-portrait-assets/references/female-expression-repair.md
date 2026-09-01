# Female cross-skin expression repair

Use this route when repairing a female `E` or `M` cell across `S01-S04`. It is
a candidate-production workflow; it never grants promotion authority.

## Locked ownership

- The accepted same-identity, same-expression cell owns geometry, registered
  coordinates, scale, angle, internal action, and feature semantics.
- The target-S reference owns tone only. It must not reshape or relocate the
  feature.
- A target-S flat field owns every pixel outside the feature during removal
  staging. Do not retain a head, jaw, neck, body, or profile gradient there.
- For `X03`, keep the complete tongue visibly beyond the lips. Teeth, specular
  highlights, and saliva remain neutral/clear; a target skin tone must not tint
  them brown or erase them.

## Fail-closed route

1. Resolve and hash the accepted geometry source, target-S tone source, exact
   1254x1254 coordinates, and exact target-S flat RGB.
2. Build or generate a full-canvas opaque donor with the feature at literal
   accepted coordinates and the exact flat target-S field everywhere else.
   A donor retaining any head/profile pixels is rejected before removal.
3. Run a literal feature-only 50/50 comparison before removal. Do not align,
   shift, resize, or warp either side. Reject any changed silhouette, tongue
   length/direction, mouth opening, teeth layout, saliva attachment, or
   coordinate drift.
4. For an M-only repair, run one fresh target-S `INSPYRENET` pass at
   `process_res=1024`, `sensitivity=1.0`, `blur=0`, `offset=0`, and
   `refine_foreground=false`. Attach the saved mask exactly once and use it
   directly. Never copy S01 alpha or crop, intersect, minimum, dilate, erode,
   splice, or cap the fresh mask to force a pass.
5. Gate the untouched mask at alpha `>=1` against the accepted same-cell owner
   support dilated by exactly 32 pixels Chebyshev distance (65x65 max filter).
   Any pixel outside support rejects the attempt; the gate is diagnostic and
   must not rewrite the mask.
6. Review isolated alpha on black, white, magenta, and checkerboard; review the
   exact target-S base assembly; and compare S01-S04 in one row. For `X03`,
   explicitly inspect the tongue-to-lip junction, tongue tip, teeth neutrality,
   and saliva end. Reject cuts, detached fragments, profile residue, or tinted
   teeth/saliva.
7. Package an accepted repair attempt as a complete identity candidate. A
   three-cell `M01/X03` repair still contains all 32 female M01 payloads; every
   unchanged payload must be byte-identical to the approved revision.
8. Bind QC and every payload SHA-256 into the candidate manifest. Promotion is
   forbidden until the user explicitly accepts that exact candidate/QC hash.

## Failure classification

- Wrong feature RGB, geometry, teeth, or saliva: regenerate from the locked
  inputs. Do not patch pixels from another attempt.
- Correct RGB with a failed native matte: rerun the approved remover on a
  corrected flat-field staging donor. Do not replace the matte with S01 alpha.
- Head/profile residue: the staging donor is wrong; rebuild the flat field
  before removal.
- Correct cell outside the repair scope: preserve its bytes.
