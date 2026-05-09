# ============================================================
# PHP Security Auditor
# Includes: PHP-CLI, Composer, composer audit
# ============================================================
FROM php:8.3-cli-alpine

LABEL maintainer="security-audit"
LABEL description="PHP + Composer security auditing container"

RUN apk add --no-cache \
    bash \
    curl \
    git \
    unzip \
    zip \
    libzip-dev \
    && docker-php-ext-install zip

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# Trust all directories for git (handles cross-ownership of mounted repos)
RUN git config --global --add safe.directory '*'

RUN php --version && composer --version

CMD ["tail", "-f", "/dev/null"]