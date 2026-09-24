<?php
namespace App\Services;

use App\Services\JwtService;
use App\Services\AuditLogger;

class AuthService implements Authenticatable
{
    public function __construct(private JwtService $jwtService, private AuditLogger $auditLogger) {}

    public function authenticate(): string
    {
        $token = $this->jwtService->createToken();
        $this->auditLogger->log();
        return $token;
    }
}
