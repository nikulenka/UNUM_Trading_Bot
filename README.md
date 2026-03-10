# Trade Bot

## Environment Configuration

### Files stored in git:
- `.env.example` - template for development environment
- `.env.test.example` - template for test environment

### Files NOT stored in git:
- `.env` - local environment variables
- `.env.dev` - development environment variables
- `.env.test` - test environment variables  
- `.env.prod` - production environment variables

### How secrets are passed:
- Through environment variables
- Through CI secrets / deployment environment

### Configuration priority:
- Environment variables have priority over env files
- For `APP_ENV=test`, safe CI-compatible DSN defaults are used if not explicitly set
