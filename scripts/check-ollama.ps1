$ErrorActionPreference = 'Stop'
$model = if ($env:OLLAMA_EMBED_MODEL) { $env:OLLAMA_EMBED_MODEL } else { 'qwen3-embedding:0.6b' }
$baseUrl = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL.TrimEnd('/') } else { 'http://127.0.0.1:11434' }

try {
    $tags = Invoke-RestMethod -Uri "$baseUrl/api/tags" -Method Get -TimeoutSec 5
} catch {
    throw "Ollama 服务不可用，请先启动 Ollama：$($_.Exception.Message)"
}

if ($tags.models.name -notcontains $model) {
    Write-Host "正在拉取轻量中文嵌入模型 $model ..."
    Invoke-RestMethod -Uri "$baseUrl/api/pull" -Method Post -ContentType 'application/json' `
        -Body (@{ name = $model; stream = $false } | ConvertTo-Json) -TimeoutSec 1800 | Out-Null
}

Write-Host "Ollama 嵌入模型已就绪：$model"

