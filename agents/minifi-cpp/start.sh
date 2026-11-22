#!/bin/sh
set -eu

if [ ! -f conf/config.yml ]; then
  cp /oem/initial-flow.json conf/config.yml
fi

sed -i -E '/^nifi\.c2\.(enable|agent\.(identifier|class|heartbeat\.period)|full\.heartbeat|rest\.(path\.base|url(\.ack)?|request\.encoding)|flow\.base\.url)=/d' conf/minifi.properties
cat >> conf/minifi.properties <<EOF
nifi.c2.enable=true
nifi.c2.agent.identifier=${OEM_CPP_AGENT_ID}
nifi.c2.agent.class=openedge-test
nifi.c2.agent.heartbeat.period=5 sec
nifi.c2.full.heartbeat=true
nifi.c2.rest.request.encoding=none
nifi.c2.rest.path.base=${OEM_CPP_C2_ORIGIN}
nifi.c2.rest.url=/c2-protocol/heartbeat
nifi.c2.rest.url.ack=/c2-protocol/acknowledge
nifi.c2.flow.base.url=${OEM_CPP_C2_ORIGIN}/c2-protocol/
EOF

exec ./bin/minifi.sh run
