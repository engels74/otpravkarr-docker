# Otpravkarr Docker Image

<p align="center">
  <img src="https://engels74.net/img/image-logos/otpravkarr.svg" alt="otpravkarr" style="width: 30%;"/>
</p>

<p align="center">
  <a href="https://github.com/engels74/otpravkarr-docker/blob/master/LICENSE"><img src="https://img.shields.io/badge/License%20(Image)-GPL--3.0-orange" alt="License (Image)"></a>
  <a href="https://github.com/engels74/otpravkarr"><img src="https://img.shields.io/badge/License%20(App)-AGPL--3.0-blue" alt="License (App)"></a>
  <a href="https://github.com/engels74/otpravkarr/stargazers"><img src="https://img.shields.io/github/stars/engels74/otpravkarr.svg" alt="GitHub Stars"></a>
</p>

## Documentation

This repository contains Docker and Docker Compose configuration for running otpravkarr in containerized environments.

For more information about the otpravkarr application, visit [github.com/engels74/otpravkarr](https://github.com/engels74/otpravkarr).

## Docker Image

### Docker Compose

To get started with otpravkarr using Docker, follow these steps:

1. **Create a Docker Compose file** (e.g., `docker-compose.yml`):
    ```yaml
    services:
      otpravkarr:
        container_name: otpravkarr
        image: ghcr.io/engels74/otpravkarr-docker:latest
        ports:
          - 3000:3000
        environment:
          - PUID=1000
          - PGID=1000
          - UMASK=002
          - TZ=Etc/UTC
          - OTPRAVKARR_SECRET=your-secret-here
        volumes:
          - ./config:/config
        restart: unless-stopped
    ```

2. **Run the Docker container:**
    ```sh
    docker compose up -d
    ```

3. **Access otpravkarr** at `http://localhost:3000`

## License

- **Docker Image**: Licensed under the GPL-3.0 License. See the [LICENSE](https://github.com/engels74/otpravkarr-docker/blob/master/LICENSE) file for details.
- **Otpravkarr Application**: Licensed under the AGPL-3.0 License. See the [otpravkarr repository](https://github.com/engels74/otpravkarr) for details.
