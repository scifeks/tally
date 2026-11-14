# TypeScript error message exposure patterns

Vulnerable-vs-safe snippets for TypeScript error handling the
`misconfig.error_message_exposure` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## NestJS exception filters

### Vulnerable

```typescript
import {
    ExceptionFilter,
    Catch,
    ArgumentsHost,
    HttpStatus
} from '@nestjs/common';

@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
    catch(exception: unknown, host: ArgumentsHost) {
        const ctx = host.switchToHttp();
        const response = ctx.getResponse();

        response.status(HttpStatus.INTERNAL_SERVER_ERROR).json({
            error: (exception as Error).message,
            stack: (exception as Error).stack
        });
    }
}
```

### Safe

```typescript
import {
    ExceptionFilter,
    Catch,
    ArgumentsHost,
    HttpStatus,
    Logger
} from '@nestjs/common';

@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
    private readonly logger = new Logger();

    catch(exception: unknown, host: ArgumentsHost) {
        const ctx = host.switchToHttp();
        const response = ctx.getResponse();

        this.logger.error((exception as Error).message);
        response.status(HttpStatus.INTERNAL_SERVER_ERROR).json({
            error: "Internal server error"
        });
    }
}
```

Log the full exception using the NestJS Logger. Return a generic error
message in the HTTP response without exposing the exception message or
stack trace.

## NestJS HttpException with internal details

### Vulnerable

```typescript
import { Controller, Get, HttpException, HttpStatus } from '@nestjs/common';

@Controller('api/data')
export class DataController {
    @Get()
    async getData() {
        try {
            return await this.service.fetch();
        } catch (error) {
            throw new HttpException(
                (error as Error).message,
                HttpStatus.INTERNAL_SERVER_ERROR
            );
        }
    }
}
```

### Safe

```typescript
import {
    Controller,
    Get,
    HttpException,
    HttpStatus,
    Logger
} from '@nestjs/common';

@Controller('api/data')
export class DataController {
    private readonly logger = new Logger();

    @Get()
    async getData() {
        try {
            return await this.service.fetch();
        } catch (error) {
            this.logger.error((error as Error).message);
            throw new HttpException(
                "Internal server error",
                HttpStatus.INTERNAL_SERVER_ERROR
            );
        }
    }
}
```

Log the exception server-side with `Logger.error()`. Throw an HttpException
with a generic message without exposing the original exception details.

## Express with TypeScript error middleware

### Vulnerable

```typescript
import express, { ErrorRequestHandler } from 'express';

const errorHandler: ErrorRequestHandler = (err, req, res, next) => {
    res.status(500).json({
        error: err.message,
        stack: err.stack
    });
};

app.use(errorHandler);

app.get('/data', (req, res) => {
    try {
        const data = fetchData();
        res.json(data);
    } catch (err: unknown) {
        res.status(500).json({
            error: (err as Error).message
        });
    }
});
```

### Safe

```typescript
import express, { ErrorRequestHandler } from 'express';
import { Logger } from 'pino';

const logger = new Logger();

const errorHandler: ErrorRequestHandler = (err, req, res, next) => {
    logger.error(err, "Unhandled error");
    res.status(500).json({
        error: "Internal server error"
    });
};

app.use(errorHandler);

app.get('/data', (req, res) => {
    try {
        const data = fetchData();
        res.json(data);
    } catch (err: unknown) {
        logger.error(err as Error, "Error fetching data");
        res.status(500).json({
            error: "Internal server error"
        });
    }
});
```

Log exceptions with a typed logger. Return a generic error message without
exposing exception details.

## Custom error DTOs with stack traces

### Vulnerable

```typescript
export interface ErrorResponse {
    error: string;
    stack?: string;
    timestamp: number;
}

export class ErrorService {
    createErrorResponse(err: Error): ErrorResponse {
        return {
            error: err.message,
            stack: err.stack,
            timestamp: Date.now()
        };
    }
}
```

### Safe

```typescript
export interface ErrorResponse {
    error: string;
    timestamp: number;
}

export class ErrorService {
    private readonly logger: Logger;

    createErrorResponse(err: Error): ErrorResponse {
        this.logger.error(err, "Error occurred");
        return {
            error: "Internal server error",
            timestamp: Date.now()
        };
    }
}
```

Log the full exception server-side. Remove stack traces and internal
exception messages from the error DTO. Return only generic error messages
in the response.
