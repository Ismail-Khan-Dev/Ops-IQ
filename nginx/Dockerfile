FROM nginx:1.27-alpine

# TLS cert boot guard — fails fast when certs are missing so nginx
# is never started without TLS. The stock /docker-entrypoint.sh and
# /docker-entrypoint.d/ scripts are preserved.
COPY cert-guard.sh /usr/local/bin/cert-guard.sh
RUN chmod +x /usr/local/bin/cert-guard.sh

ENTRYPOINT ["/usr/local/bin/cert-guard.sh"]
CMD ["nginx", "-g", "daemon off;"]