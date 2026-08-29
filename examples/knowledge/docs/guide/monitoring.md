# Monitoring and alerts

The console has a "Monitoring" section: logs, service metrics, and
configurable alerts. Alerts arrive in the console, by email, or in the
corporate chat.

## Enabling

Monitoring is enabled in the organization settings with a single switch.
After enabling, the platform collects logs and metrics for all services and
shows them on the dashboard.

## Metrics

The dashboard shows:

- CPU and memory usage of services;
- the number of active projects and calculations;
- API response time;
- the background job queue.

Data is kept for 30 days; the retention period can be extended if needed.

## Alerts

Alert rules are defined in the "Rules" section:

- "service unavailable" — fires when a response is lost for longer than 60 seconds;
- "queue growing" — when the number of waiting jobs rises above the threshold;
- "API errors" — when the share of 5xx responses exceeds the given percentage.

Each rule has a threshold, a check interval, and a recipient list. A trigger
is written to the incident log; re-notification happens only after
acknowledgement.

## Integrations

Notifications can be sent to a Slack or Telegram channel through a webhook by
providing the URL in the rule settings. Metrics can be exported to Prometheus
for external dashboards.

## Incidents

The incident log stores the history of every trigger: time, rule, status, and
who acknowledged. This helps track recurring problems and verify the effect of
fixes.