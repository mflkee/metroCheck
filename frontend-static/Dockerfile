FROM nginx:alpine

COPY backend/app/static/index.html /usr/share/nginx/html/index.html
COPY frontend-static/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
