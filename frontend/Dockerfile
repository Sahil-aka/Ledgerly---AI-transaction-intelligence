FROM nginx:1.27-alpine
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY frontend/index.html frontend/styles.css frontend/app.js /usr/share/nginx/html/
COPY transactions.csv /usr/share/nginx/html/sample-transactions.csv
EXPOSE 80
