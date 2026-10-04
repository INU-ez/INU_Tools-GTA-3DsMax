-- INU Tools native launcher. The localized rollout is compiled by inu_boot.
global INU_ROOT = pathConfig.removePathLeaf (getThisScriptFilename())
global INU_launch
global INU_boot
(
    local inuCmd = "import sys\np = r'" + INU_ROOT + "'\nif p not in sys.path: sys.path.insert(0, p)"
    python.execute inuCmd
    (python.import "inu_boot").register_launcher INU_ROOT
)
