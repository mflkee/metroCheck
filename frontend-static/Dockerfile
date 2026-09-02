FROM nginx:alpine

COPY backend/app/static/index.html /usr/share/nginx/html/index.html
COPY backend/app/static/favicon.svg /usr/share/nginx/html/favicon.svg
COPY frontend-static/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
