# RC77 architectural overview illustration

An additional editable slide is inserted after the two modular architecture slides, before deployment. It shows an original, people-free, photographic CGI scene of CIR components and their relationships: the Flask/Gunicorn core, PostgreSQL/database persistence, workflows and conditional logic, notifications, PDF/report generation, identity, AlBot and Alfresco integrations, and Linux container/orchestration deployment options.

The artwork itself contains no slide header/footer and does not reuse stock photography or show real persons. Technology labels and explanatory content remain native, editable PowerPoint elements. The standalone synthetic image is SHA-256 catalogued in `visual_rc77_art/provenance.json`.

Deployment claims are grounded in `README.md` and `docs/DEPLOYMENT.md`: Docker/Podman, Kubernetes/OpenShift/Helm and linux/amd64 + linux/arm64. Source slides count is now **88**; the verified CI gallery starts at slide 89. The documentation validator, PDF gallery verifier and evidence sealer are adjusted to that numbering. The GitHub CI must still confirm the final same-run authentic screenshot PDF/PPTX build after merge.
