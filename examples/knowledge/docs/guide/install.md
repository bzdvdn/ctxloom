# Platform installation

The platform is installed with the installer, the `nexusrd install` command.
The installer runs on Linux and macOS; a console build is available for
Windows.

## System requirements

- 4 CPU cores, 8 GB of RAM, 20 GB of disk space;
- Docker or a local container runtime;
- internet access for the first start (downloading models and integrations).

## Installation steps

1. Download the installer for your system.
2. Run `nexusrd install` and follow the prompts.
3. Provide the authorization service address or keep local mode.
4. Wait for the check: the `nexusrd status` command shows the service state.

## Revit and AutoCAD plugins

Working with BIM editors requires separate plugins from the catalog:

- Autodesk Revit plugin — area and schedule calculations right in the model;
- AutoCAD plugin — exchanging drawings and specifications.

Plugins are enabled in the editor through the "Add-ins → CTXSPACE" menu;
versions update through the platform catalog.

## After installation

Sign in through SSO, add the integration with your Git repository, and upload
the material catalog. Done — you can create your first project.