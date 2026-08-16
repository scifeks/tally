# TypeScript mass assignment patterns

Vulnerable-vs-safe snippets for the TypeScript-specific ORMs the
`access_control.mass_assignment` scanner recognizes.

## NestJS DTO without field validation

### Vulnerable

```typescript
import { Controller, Post, Body, Put, Param } from '@nestjs/common';
import { UserService } from './user.service';

@Controller('users')
export class UserController {
  constructor(private userService: UserService) {}

  @Post()
  async create(@Body() userData: any) {
    return this.userService.create(userData);
  }

  @Put(':id')
  async update(@Param('id') id: string, @Body() userData: any) {
    return this.userService.update(id, userData);
  }
}

export class UserService {
  async create(data: any) {
    return User.create(data);
  }

  async update(id: string, data: any) {
    return User.update({ id }, data);
  }
}
```

An attacker can set any field in the User model.

### Safe

```typescript
import { Controller, Post, Body, Put, Param } from '@nestjs/common';
import { IsEmail, IsString, MaxLength } from 'class-validator';
import { UserService } from './user.service';

export class CreateUserDto {
  @IsString()
  @MaxLength(100)
  username: string;

  @IsEmail()
  email: string;

  @IsString()
  password: string;
}

export class UpdateUserDto {
  @IsEmail()
  email?: string;

  @IsString()
  @MaxLength(100)
  username?: string;
}

@Controller('users')
export class UserController {
  constructor(private userService: UserService) {}

  @Post()
  async create(@Body() userData: CreateUserDto) {
    return this.userService.create(userData);
  }

  @Put(':id')
  async update(
    @Param('id') id: string,
    @Body() userData: UpdateUserDto,
  ) {
    return this.userService.update(id, userData);
  }
}

export class UserService {
  async create(data: CreateUserDto) {
    return User.create(data);
  }

  async update(id: string, data: UpdateUserDto) {
    return User.update({ id }, data);
  }
}
```

Define explicit DTOs for each endpoint. Use validation decorators to
restrict field types and presence. Only fields in the DTO are accepted.

## Prisma with request data

### Vulnerable

```typescript
import { PrismaClient } from '@prisma/client';
import { Request } from 'express';

const prisma = new PrismaClient();

export async function createUser(req: Request) {
  return prisma.user.create({
    data: req.body,
  });
}

export async function updateUser(id: string, req: Request) {
  return prisma.user.update({
    where: { id },
    data: req.body,
  });
}
```

Prisma accepts all properties from `req.body`.

### Safe

```typescript
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

interface CreateUserInput {
  username: string;
  email: string;
  password: string;
}

interface UpdateUserInput {
  email?: string;
  username?: string;
}

export async function createUser(data: CreateUserInput) {
  return prisma.user.create({
    data: {
      username: data.username,
      email: data.email,
      password: data.password,
    },
  });
}

export async function updateUser(id: string, data: UpdateUserInput) {
  const updateData: Partial<UpdateUserInput> = {};
  if (data.email) updateData.email = data.email;
  if (data.username) updateData.username = data.username;

  return prisma.user.update({
    where: { id },
    data: updateData,
  });
}
```

Filter the input before passing to Prisma. Use typed interfaces to
restrict which fields are passed.

## TypeORM repository with unfiltered data

### Vulnerable

```typescript
import { getRepository } from 'typeorm';
import { User } from './entity/User';

const userRepository = getRepository(User);

export async function createUser(data: any) {
  const user = userRepository.create(data);
  return userRepository.save(user);
}

export async function updateUser(id: number, data: any) {
  return userRepository.update(id, data);
}
```

TypeORM assigns all properties from `data` to the entity.

### Safe

```typescript
import { getRepository } from 'typeorm';
import { User } from './entity/User';

interface CreateUserInput {
  username: string;
  email: string;
  password: string;
}

interface UpdateUserInput {
  email?: string;
  username?: string;
}

const userRepository = getRepository(User);

export async function createUser(input: CreateUserInput) {
  const user = userRepository.create({
    username: input.username,
    email: input.email,
    password: input.password,
  });
  return userRepository.save(user);
}

export async function updateUser(id: number, input: UpdateUserInput) {
  const updateData: Partial<UpdateUserInput> = {};
  if (input.email) updateData.email = input.email;
  if (input.username) updateData.username = input.username;

  return userRepository.update(id, updateData);
}
```

Explicitly map input properties to entity fields. Use typed interfaces
to restrict available fields.

## Sequelize with TypeScript

### Vulnerable

```typescript
import { Model, DataTypes } from 'sequelize';

const sequelize = new Sequelize('database', 'user', 'password');

export class User extends Model {}

User.init(
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
    },
    username: DataTypes.STRING,
    email: DataTypes.STRING,
    is_admin: DataTypes.BOOLEAN,
  },
  { sequelize },
);

export async function createUser(data: any) {
  return User.create(data);
}

export async function updateUser(id: number, data: any) {
  const user = await User.findByPk(id);
  await user.update(data);
  return user;
}
```

An attacker can set any column.

### Safe

```typescript
import { Model, DataTypes } from 'sequelize';

interface UserInput {
  username: string;
  email: string;
  password: string;
}

export class User extends Model {}

User.init(
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
    },
    username: DataTypes.STRING,
    email: DataTypes.STRING,
    is_admin: DataTypes.BOOLEAN,
  },
  { sequelize },
);

export async function createUser(data: UserInput) {
  return User.create(
    {
      username: data.username,
      email: data.email,
      password: data.password,
    },
    { fields: ['username', 'email', 'password'] },
  );
}

export async function updateUser(id: number, data: Partial<UserInput>) {
  const user = await User.findByPk(id);
  await user.update(data, {
    fields: ['username', 'email'],
  });
  return user;
}
```

Use the `fields` option to whitelist updatable columns. Filter input
to an interface with only allowed properties.
