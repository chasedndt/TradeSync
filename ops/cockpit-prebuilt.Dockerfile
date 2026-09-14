# Low-memory packaging path: run npm run build in services/cockpit-ui first.
# Context must be services/cockpit-ui. This packages the tested local artifact;
# it does not compile source or install dependencies inside the live Docker VM.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/ /usr/share/nginx/html/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
