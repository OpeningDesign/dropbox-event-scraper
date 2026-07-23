FROM mhart/alpine-node:16
MAINTAINER Ayush agb.ayushgupta@gmail.com

RUN mkdir -p /scraper
WORKDIR /scraper

COPY package.json package-lock.json ./
RUN npm install

COPY . ./

# options.json and the CSV are mounted at runtime (see .dockerignore), so
# editing credentials or dates does not require a rebuild
RUN mkdir -p /scraper/out
ENV CSV_OUTPUT_PATH=/scraper/out/output.csv

CMD ["npm", "start"]
