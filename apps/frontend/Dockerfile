FROM node:22-slim AS dev

# Версию pnpm corepack берёт из поля packageManager в package.json. Без него
# он тянет «последнюю известную» и тихо расходится с pnpm-lock.yaml.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN corepack enable

WORKDIR /app

# Зависимости ставятся на этапе сборки и живут в образе, а не в томе с
# исходниками: иначе каждый `up` начинался бы с pnpm install.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173

# `pnpm exec vite`, а не `pnpm dev`: скрипт из package.json пришлось бы звать
# с флагами, а pnpm пробрасывает их в скрипты по-разному от версии к версии.
CMD ["pnpm", "exec", "vite", "--host", "0.0.0.0", "--port", "5173"]
