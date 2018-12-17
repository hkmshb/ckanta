# ckanta

CKAN Task Automator (CKANTA) is a command-line tool for automating CKAN management tasks
using the CKAN API.

## Configuration & Command Settings

CKANTA can pick configuration and command settings from `~/.config/ckanta.conf` with
settings for multiple CKAN instances and some other CKANTA-wide settings accessible
from the context object using the `get_config` method.

```ini
# instance setting
[instance:<name-1>]
urlbase={url-1}
apikey={guid-1}

[instance:<name-2>]
urlbase={url-2}
apikey={guid-2}

# ckanta-wide settings accessible using `context.get_config`
[ckanta]
key=value
key=value
national-state = nigeria
national-states =
   AB:Abia  AD:Adamawa  AK:'Akwa Ibom'  AN:Anambra
   BA:Bauchi  BE:Benue  BR:Borno  BY:Bayelsa
   CR:'Cross River' ...
```