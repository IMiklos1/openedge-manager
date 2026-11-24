#!/bin/sh
set -eu

# Use the image's configuration in its persistent conf volume.
cd "$NIFI_HOME"
sed -i \
  -e 's/^nifi.security.keystore=.*/nifi.security.keystore=/' \
  -e 's/^nifi.security.truststore=.*/nifi.security.truststore=/' \
  -e 's/^nifi.security.user.login.identity.provider=.*/nifi.security.user.login.identity.provider=/' \
  -e 's/^nifi.web.https.host=.*/nifi.web.https.host=/' \
  -e 's/^nifi.web.https.port=.*/nifi.web.https.port=/' \
  -e 's/^nifi.web.http.host=.*/nifi.web.http.host=0.0.0.0/' \
  -e 's/^nifi.web.http.port=.*/nifi.web.http.port=8080/' \
  -e 's/^nifi.remote.input.host=.*/nifi.remote.input.host=nifi/' \
  -e 's/^nifi.remote.input.socket.port=.*/nifi.remote.input.socket.port=/' \
  -e 's/^nifi.remote.input.secure=.*/nifi.remote.input.secure=false/' \
  -e 's/^nifi.remote.input.http.enabled=.*/nifi.remote.input.http.enabled=true/' \
  conf/nifi.properties
sed -i -e 's/^java.arg.2=.*/java.arg.2=-Xms512m/' -e 's/^java.arg.3=.*/java.arg.3=-Xmx1g/' conf/bootstrap.conf
exec bin/nifi.sh run
