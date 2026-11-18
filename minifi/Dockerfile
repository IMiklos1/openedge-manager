FROM apache/nifi-minifi-cpp:1.1.0@sha256:647d0548f8411aeb7fc58def0666077c25f950ba85cf5cc58d4d28500b58e0cd

COPY --chown=minificpp:minificpp --chmod=0644 agent-01/conf/config.yml ./conf/config.yml
COPY --chmod=0644 agent-01/conf/minifi.properties /tmp/oem-c2.properties
RUN sed -i '/^nifi\.c2\.root\.classes=/d; /^nifi\.c2\.full\.heartbeat=/d' conf/minifi.properties \
    && printf '\n' >> conf/minifi.properties \
    && cat /tmp/oem-c2.properties >> conf/minifi.properties
