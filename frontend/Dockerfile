FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY public /usr/share/nginx/html
COPY docker-entrypoint.sh /docker-entrypoint.d/40-simple-order-pay-config.sh

RUN chmod +x /docker-entrypoint.d/40-simple-order-pay-config.sh

EXPOSE 80
