# Builds and runs the React/Vite OT-SOAR management dashboard.

FROM node:22-alpine

WORKDIR /app

COPY dashboard/package.json dashboard/package-lock.json /app/

RUN npm ci

COPY dashboard /app

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
