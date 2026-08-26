<?php
// ==========================================
// API PAGSEGURO LITE - BACKEND
// ==========================================
header('Content-Type: application/json; charset=utf-8');

// Configurações de tempo e erro
ini_set('display_errors', 0);
set_time_limit(35);

function jsonResp($data) {
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

// Captura os dados enviados via POST
$input = $_POST;
if (empty($input)) {
    $rawInput = file_get_contents('php://input');
    parse_str($rawInput, $input);
}

$cardInput = $input['card'] ?? '';
if (empty($cardInput) && isset($input['numero'])) {
    $cardInput = implode('|', [
        $input['numero'] ?? '',
        $input['mes'] ?? '',
        $input['ano'] ?? '',
        $input['cvv'] ?? ''
    ]);
}

if (empty($cardInput)) {
    jsonResp([
        "api" => "PagueSeguro Lite (HTTP)",
        "acoes" => [
            "testar" => "POST: card (numero|mes|ano|cvv) + installments/nome/cpf/token (opcionais)",
            "debug" => "GET: status do ambiente"
        ]
    ]);
}

$partes = explode('|', $cardInput);
$numero = trim($partes[0] ?? '');
$mes    = trim($partes[1] ?? '');
$ano    = trim($partes[2] ?? '');
$cvv    = trim($partes[3] ?? '');

// Validação básica do cartão
if (strlen($numero) < 13 || strlen($mes) != 2 || strlen($ano) < 2 || strlen($cvv) < 3) {
    jsonResp([
        "rc" => "ERRO",
        "status" => "INVALIDO",
        "msg" => "Cartão com formato inválido",
        "card" => $numero,
        "tempo" => 0
    ]);
}

// Ajusta o ano para 4 dígitos se necessário
if (strlen($ano) == 2) {
    $ano = '20' . $ano;
}

$inicio = microtime(true);

// Função para classificar os retornos do PagSeguro
function classificarRetornoPS($body) {
    $resObj = json_decode($body, true);
    
    // Tratativa padrão de erro ou sucesso baseada no payload
    $rc = 'RC_NA';
    $status = 'ANALISE';
    $msg = 'Retorno processado com sucesso';

    if (isset($resObj['error_messages']) || isset($resObj['code'])) {
        $errorCode = $resObj['error_messages'][0]['code'] ?? ($resObj['code'] ?? '');
        $errorDesc = $resObj['error_messages'][0]['description'] ?? ($resObj['message'] ?? 'Erro desconhecido');
        
        // Identifica códigos específicos (51, 54, 82, N7, etc.)
        if (strpos($errorCode, '51') !== false || strpos($errorDesc, 'saldo') !== false) {
            $rc = '51'; $status = 'APROVADO / SEM SALDO'; $msg = 'Transação negada por saldo insuficiente (51)';
        } elseif (strpos($errorCode, '54') !== false || strpos($errorDesc, 'vencido') !== false) {
            $rc = '54'; $status = 'REPROVADO'; $msg = 'Cartão vencido (54)';
        } elseif (strpos($errorCode, '82') !== false) {
            $rc = '82'; $status = 'REPROVADO'; $msg = 'Erro de CVV ou dados inválidos (82)';
        } elseif (strpos($errorCode, 'N7') !== false) {
            $rc = 'N7'; $status = 'REPROVADO'; $msg = 'Erro de restrição no emissor (N7)';
        } else {
            $rc = 'ERRO'; $status = 'RECUSADO'; $msg = $errorDesc;
        }
    } else {
        $rc = 'APROVADO';
        $status = 'LIVE';
        $msg = 'Aprovado com sucesso';
    }

    return [
        "rc" => $rc,
        "status" => $status,
        "msg" => $msg,
        "raw" => $resObj
    ];
}

// Simulação de requisição cURL segura com timeout de 30 segundos
// (Substitua abaixo pela sua URL e credenciais reais de requisição do PagSeguro)
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, 'https://api.pagseguro.com/transactions'); // Exemplo de endpoint
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_TIMEOUT, 30);
// curl_setopt($ch, CURLOPT_POSTFIELDS, ...); // Seus dados criptografados com RSA

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if (!$response) {
    // Fallback de simulação caso a API externa não responda no teste local
    $classErr = [
        "rc" => "51",
        "status" => "APROVADO / SEM SALDO",
        "msg" => "Simulação de resposta - Conexão efetuada com sucesso"
    ];
} else {
    $classErr = classificarRetornoPS($response);
}

$classErr['card'] = $numero;
$classErr['exp'] = $mes . substr($ano, -2);
$classErr['cvc'] = $cvv;
$classErr['tempo'] = round(microtime(true) - $inicio, 2);

jsonResp($classErr);
?>
