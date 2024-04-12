Build and run the first domain

```bash
bash -c '\
docker build -f domain1.dockerfile . -t domain1 && \
docker run --name domain1 -it -p 2001:1001 domain1'
```

Check with

```bash
curl localhost:2001
```

Build and run the second domain

```bash
bash -c '\
docker build -f domain2.dockerfile . -t domain2 && \
docker run --name domain2 -it -p 2002:1002 domain2'
```

Check with

```bash
curl localhost:2002
```

Build the rathole image and run a rathole server

```bash
bash -c '\
docker build -f rathole.dockerfile . -t rathole && \
docker run --name rathole-server -it -p 8001:8001 -p 8002:8002 -p 2333:2333 -e MODE=server rathole'
```

Run `curl localhost:8001` or `curl localhost:8002` should return `Recv failure: Connection reset by peer`

Run a rathole client

```bash
docker run --name rathole-client -it -e MODE=client rathole
```

The rathole server's logs should show `service=domain1: Listening at 0.0.0.0:8001` and `service=domain2: Listening at 0.0.0.0:8002` and the client's log should show `service=domain1: Control channel established` and `service=domain2: Control channel established`

Check with

```bash
curl localhost:8001
```

should send a `GET` request to the `domain1`, and

```bash
curl localhost:8002
```

should send a `GET` request to `domain2`
