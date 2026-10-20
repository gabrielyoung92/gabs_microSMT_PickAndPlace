# KiCad recovery tools

- Read README.md and RECOVERY_NOTES.md. Run commands from the repository root.
- Use canonical MicroSMT ZIP/PDF sources; retain attribution and original bytes.
- Generators can overwrite CAD and reports. Use a disposable checkout after
  manual design work; never regenerate over an unreviewed redesign.
- Check source paths and pad/net/drill parity, then native KiCad exports against
  CAM geometry. A preview or successful compilation is not hardware validation.
- Keep intermediates in ignored build/kicad/; publish only portable evidence.
