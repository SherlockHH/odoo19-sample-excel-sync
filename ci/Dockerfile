FROM odoo:19.0
USER root
COPY requirements.txt /tmp/sample-excel-requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/sample-excel-requirements.txt
USER odoo
