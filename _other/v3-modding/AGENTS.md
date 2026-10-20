# Working in this project

- Read the latest owner request, README.md, TODO.md and the relevant source audit.
- Canonical upstream files are in the two `../../{Bing-feeder,Microsmt-PNPv3}/` directories.
  Hardware recovery tools use those source directories at the repository root.
  Put custom code in `firmware/`.
- Use `make check` for changes to the firmware core or import tooling. Run
  `make arm-check` when changing the portable C code if the toolchain is available.
- Keep downloaded facts, design assumptions, code tests and physical measurements
  distinct. Basic stock-machine tests are recorded in docs/machine-setup-status.md;
  feeder prototypes and full machine calibration remain unvalidated.
- Retain the stock motion system initially. Feeder development is a separate
  subsystem, and the physical bus and exact board target are not selected yet.
- Keep firmware faults observable. Do not report feed completion based solely on
  elapsed time, receipt of a command, or transmission of a pulse.
- Hardware flashing is not authorized. Live stock-machine operation has been
  owner-authorized for the documented tests; follow the current session request
  rather than treating past tests as authorization for new unattended motion.
- Keep `.local/` out of commits. It preserves original Git metadata and private
  machine evidence. Do not change repository visibility without the owner's request.
- Keep personal details, purchase plans, private conversations and machine-specific
  filesystem paths out of tracked documentation and commit metadata. Use the
  repository-scoped no-reply Git identity. Documentation should describe the
  project, its evidence and validation status.

- Hardware reference projects live in `hardware/`. Read `hardware/RECOVERY_NOTES.md`
  before editing them. Recovery generators overwrite generated CAD files; run them
  in a disposable checkout after manual design work begins. Validate native
  schematic/PCB parity and compare CAM geometry rather than treating a rendered
  preview as evidence of correct connectivity.
