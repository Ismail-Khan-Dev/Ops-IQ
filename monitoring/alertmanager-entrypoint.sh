#!/bin/sh
# Alertmanager entrypoint - substitutes environment variables in config template

set -e

# Substitute env vars in template
envsubst < /etc/alertmanager/alertmanager.yml.tmpl > /etc/alertmanager/alertmanager.yml

# Execute the original entrypoint
exec /bin/alertmanager --config.file=/etc/alertmanager/alertmanager.yml --storage.path=/alertmanager "$@"