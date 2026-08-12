FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# Dev image, but there is no reason for the dev server to be root either —
# a container that runs as root is one bind-mount away from writing root-owned
# files into the developer's working tree. `node` is provided by the base image.
USER node

CMD ["npx", "vite", "--host", "0.0.0.0"]
