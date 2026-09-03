<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mercado Livre - Brasil</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        body {
            background-color: #ededed;
            color: #333;
        }
        
        /* TOPO AMARELO FIXO */
        .header {
            background-color: #fff159;
            padding: 10px 12px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        .header-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }
        .logo {
            display: flex;
            align-items: center;
        }
        .logo img {
            width: 46px;
            height: 34px;
            object-fit: contain;
        }
        .search-box {
            display: flex;
            flex: 1;
            background: #fff;
            border-radius: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.15);
            height: 38px;
            align-items: center;
            padding: 0 14px;
        }
        .search-box input {
            width: 100%;
            border: none;
            outline: none;
            font-size: 14px;
            background: transparent;
            color: #333;
        }
        .search-box input::placeholder {
            color: #999;
        }
        .search-box span {
            color: #666;
            font-size: 15px;
        }
        .header-icons {
            display: flex;
            gap: 16px;
            align-items: center;
            font-size: 20px;
            color: #333;
        }

        /* ATALHOS CIRCULARES (BOLINHAS) */
        .shortcuts-container {
            background-color: #fff159;
            padding: 4px 10px 14px 10px;
            overflow-x: auto;
            display: flex;
            gap: 16px;
        }
        .shortcuts-container::-webkit-scrollbar {
            display: none;
        }
        .shortcut-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            min-width: 64px;
            text-align: center;
            text-decoration: none;
        }
        .shortcut-circle {
            width: 54px;
            height: 54px;
            background: #fff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
            margin-bottom: 5px;
            font-size: 22px;
        }
        .shortcut-item span {
            font-size: 11px;
            color: #333;
            line-height: 1.2;
            font-weight: 500;
        }

        /* CONTAINER PRINCIPAL */
        .main-container {
            padding: 12px;
            max-width: 1200px;
            margin: 0 auto;
        }

        /* BLOCOS DE CATEGORIAS / OFERTAS */
        .grid-categories {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            margin-bottom: 15px;
            padding-bottom: 4px;
        }
        .grid-categories::-webkit-scrollbar {
            display: none;
        }
        .cat-box {
            background: #fff;
            border-radius: 6px;
            min-width: 115px;
            width: 115px;
            text-align: center;
            padding: 12px 8px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.08);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            text-decoration: none;
        }
        .cat-box .cat-icon {
            font-size: 28px;
            margin-bottom: 8px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .cat-box span {
            font-size: 11px;
            color: #333;
            font-weight: bold;
        }

        /* CARDS DE LOCALIZAÇÃO E BENEFÍCIOS */
        .card-section {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            margin-bottom: 15px;
            padding-bottom: 4px;
        }
        .card-section::-webkit-scrollbar {
            display: none;
        }
        .info-card {
            background: #fff;
            border-radius: 6px;
            min-width: 175px;
            width: 175px;
            padding: 15px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.08);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .info-card h4 {
            font-size: 13px;
            color: #333;
            margin-bottom: 6px;
            font-weight: bold;
        }
        .info-card p {
            font-size: 11px;
            color: #666;
            margin-bottom: 12px;
            line-height: 1.3;
        }
        .btn-blue {
            background-color: #3483fa;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px;
            font-size: 11px;
            font-weight: bold;
            cursor: pointer;
            text-align: center;
            width: 100%;
        }

        /* SEÇÃO DE PRODUTOS RECOMENDADOS */
        .section-title {
            font-size: 18px;
            color: #333;
            margin-bottom: 10px;
            font-weight: normal;
        }
        .products-grid {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding-bottom: 10px;
        }
        .products-grid::-webkit-scrollbar {
            display: none;
        }
        .product-card {
            background: #fff;
            border-radius: 6px;
            min-width: 160px;
            width: 160px;
            padding: 10px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.08);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            text-decoration: none;
        }
        .product-img {
            width: 100%;
            height: 130px;
            background: #f5f5f5;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 30px;
            border-radius: 4px;
            margin-bottom: 8px;
        }
        .product-price-area {
            margin-bottom: 4px;
        }
        .price {
            font-size: 20px;
            color: #333;
            font-weight: 400;
        }
        .discount {
            color: #00a650;
            font-size: 12px;
            margin-left: 4px;
            font-weight: 600;
        }
        .shipping {
            color: #00a650;
            font-size: 11px;
            font-weight: bold;
            margin-bottom: 4px;
        }
        .title {
            font-size: 12px;
            color: #666;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            line-height: 1.3;
        }
    </style>
</head>
<body>

    <!-- TOPO DO SITE -->
    <header class="header">
        <div class="header-top">
            <a href="index.php" class="logo">
                <img src="https://http2.mlstatic.com/frontend-assets/ui-navigation/5.19.0/mercadolibre/logo__small@2x.png" alt="Mercado Livre">
            </a>
            <div class="search-box">
                <input type="text" placeholder="Estou buscando...">
                <span>🔍</span>
            </div>
            <div class="header-icons">
                <span>☰</span>
                <span>🛒</span>
            </div>
        </div>
    </header>

    <!-- ATALHOS CIRCULARES DO TOPO (PRONTOS PARA PHP) -->
    <div class="shortcuts-container">
        <a href="catalogo.php?cat=mercadopago" class="shortcut-item">
            <div class="shortcut-circle">🤝</div>
            <span>Mercado Pago</span>
        </a>
        <a href="catalogo.php?cat=ofertas" class="shortcut-item">
            <div class="shortcut-circle">🏷️</div>
            <span>Ofertaço</span>
        </a>
        <a href="catalogo.php?cat=supermercado" class="shortcut-item">
            <div class="shortcut-circle">📦</div>
            <span>Supermercado</span>
        </a>
        <a href="catalogo.php?cat=mais-vendidos" class="shortcut-item">
            <div class="shortcut-circle">⭐</div>
            <span>Mais vendidos</span>
        </a>
        <a href="catalogo.php?cat=veiculos" class="shortcut-item">
            <div class="shortcut-circle">🚗</div>
            <span>Veículos</span>
        </a>
    </div>

    <!-- CONTEÚDO PRINCIPAL -->
    <div class="main-container">

        <!-- CATEGORIAS EM GRADE -->
        <div class="grid-categories">
            <a href="catalogo.php?cat=ofertaco" class="cat-box">
                <div class="cat-icon">⚡</div>
                <span>OFERTAÇO</span>
            </a>
            <a href="catalogo.php?cat=ate-999" class="cat-box">
                <div class="cat-icon">📱</div>
                <span>ATÉ R$999</span>
            </a>
            <a href="catalogo.php?cat=ate-1999" class="cat-box">
                <div class="cat-icon">💻</div>
                <span>ATÉ R$1.999</span>
            </a>
            <a href="catalogo.php?cat=achadinhos" class="cat-box">
                <div class="cat-icon">🛍️</div>
                <span>ACHADINHOS</span>
            </a>
        </div>

        <!-- CARDS DE LOCALIZAÇÃO E BENEFÍCIOS -->
        <div class="card-section">
            <div class="info-card">
                <div>
                    <h4>Insira sua localização</h4>
                    <p>Confira custos e prazos de entrega.</p>
                </div>
                <button class="btn-blue">Informar localização</button>
            </div>

            <div class="info-card">
                <div>
                    <h4>MENOS DE R$100</h4>
                    <p>Confira produtos com preços baixos.</p>
                </div>
                <button class="btn-blue">Mostrar produtos</button>
            </div>
        </div>

        <!-- PRODUTOS RECOMENDADOS (DIRECIONANDO PARA PRODUTO.PHP) -->
        <h2 class="section-title">Baseado nas suas últimas visitas</h2>
        <div class="products-grid">
            
            <a href="produto.php?id=1" class="product-card">
                <div class="product-img">📱</div>
                <div>
                    <div class="product-price-area">
                        <span class="price">R$ 1.499</span>
                        <span class="discount">25% OFF</span>
                    </div>
                    <div class="shipping">Frete grátis</div>
                    <div class="title">Smartphone Exemplo Modelo X 128gb Original</div>
                </div>
            </a>

            <a href="produto.php?id=2" class="product-card">
                <div class="product-img">🎧</div>
                <div>
                    <div class="product-price-area">
                        <span class="price">R$ 189</span>
                        <span class="discount">10% OFF</span>
                    </div>
                    <div class="shipping">Frete grátis</div>
                    <div class="title">Fone Headset Gamer Bluetooth Sem Fio</div>
                </div>
            </a>

        </div>

    </div>

</body>
</html>
