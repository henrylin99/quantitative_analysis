#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI专业化改造演示服务
简化的Flask应用，展示新的专业金融主题
"""

from flask import Flask, render_template_string, jsonify
import os

app = Flask(__name__)

# 设置静态文件路径
app.static_folder = 'app/static'

# HTML模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>股票分析系统 - UI专业化改造演示</title>
    
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Font Awesome -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <!-- 专业金融主题样式 -->
    <link href="/static/css/financial-theme.css" rel="stylesheet">
    <!-- 移动端响应式样式 -->
    <link href="/static/css/responsive-financial.css" rel="stylesheet">
</head>
<body>
    <!-- 导航栏 -->
    <nav class="navbar navbar-expand-lg navbar-financial fixed-top">
        <div class="container-fluid">
            <a class="navbar-brand d-flex align-items-center" href="/">
                <i class="fas fa-chart-line me-2"></i>
                <span>股票分析系统</span>
            </a>
            
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon">
                    <i class="fas fa-bars text-white"></i>
                </span>
            </button>
            
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link active" href="/">
                            <i class="fas fa-home me-1"></i>首页
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="#features">
                            <i class="fas fa-star me-1"></i>功能特色
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="#demo">
                            <i class="fas fa-desktop me-1"></i>界面演示
                        </a>
                    </li>
                </ul>
                
                <!-- 实时状态指示器 -->
                <div class="navbar-nav">
                    <div class="nav-item d-flex align-items-center me-3">
                        <span class="real-time-indicator">UI演示模式</span>
                    </div>
                    <div class="nav-item">
                        <button class="btn btn-outline-light btn-sm" onclick="location.reload()">
                            <i class="fas fa-sync-alt me-1"></i>刷新
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </nav>

    <!-- 主要内容区域 -->
    <main class="main-content" style="margin-top: 76px; min-height: calc(100vh - 76px);">
        <div class="container">
            <!-- 欢迎横幅 -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card stock-info-banner animate-fade-in-up">
                        <div class="card-body text-center py-5">
                            <h1 class="display-4 mb-3">🎨 UI专业化改造演示</h1>
                            <p class="lead">全新的专业金融主题，现代化的用户界面设计</p>
                            <p class="mb-4">响应式设计 • 微交互动画 • 可访问性优化 • 移动端适配</p>
                            <div class="d-grid gap-2 d-md-block">
                                <button class="btn btn-light btn-lg me-md-3 btn-financial" onclick="scrollToSection('features')">查看特色</button>
                                <button class="btn btn-outline-light btn-lg btn-financial" onclick="scrollToSection('demo')">界面演示</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 功能特色 -->
            <div class="row mb-4" id="features">
                <div class="col-12">
                    <h2 class="mb-4">✨ 改造特色</h2>
                </div>
            </div>

            <div class="row g-3 g-md-4 mb-5">
                <!-- 专业主题 -->
                <div class="col-6 col-md-6 col-lg-3">
                    <div class="card metric-card-enhanced h-100 hover-lift animate-fade-in-left">
                        <div class="card-body text-center">
                            <div class="metric-icon">
                                <i class="fas fa-palette text-primary"></i>
                            </div>
                            <h5 class="card-title">专业主题</h5>
                            <p class="card-text">金融行业专业色彩搭配，现代化视觉设计</p>
                            <button class="btn btn-primary-financial" onclick="showFeatureDemo('theme')">查看演示</button>
                        </div>
                    </div>
                </div>

                <!-- 响应式设计 -->
                <div class="col-6 col-md-6 col-lg-3">
                    <div class="card metric-card-enhanced h-100 hover-lift animate-fade-in-left">
                        <div class="card-body text-center">
                            <div class="metric-icon">
                                <i class="fas fa-mobile-alt text-success"></i>
                            </div>
                            <h5 class="card-title">响应式设计</h5>
                            <p class="card-text">完美适配桌面、平板、手机等各种设备</p>
                            <button class="btn btn-success-financial" onclick="showFeatureDemo('responsive')">查看演示</button>
                        </div>
                    </div>
                </div>

                <!-- 微交互动画 -->
                <div class="col-6 col-md-6 col-lg-3">
                    <div class="card metric-card-enhanced h-100 hover-lift animate-fade-in-left">
                        <div class="card-body text-center">
                            <div class="metric-icon">
                                <i class="fas fa-magic text-warning"></i>
                            </div>
                            <h5 class="card-title">微交互动画</h5>
                            <p class="card-text">丰富的动画效果，提升用户体验</p>
                            <button class="btn btn-warning-financial" onclick="showFeatureDemo('animation')">查看演示</button>
                        </div>
                    </div>
                </div>

                <!-- 可访问性 -->
                <div class="col-6 col-md-6 col-lg-3">
                    <div class="card metric-card-enhanced h-100 hover-lift animate-fade-in-left">
                        <div class="card-body text-center">
                            <div class="metric-icon">
                                <i class="fas fa-universal-access text-info"></i>
                            </div>
                            <h5 class="card-title">可访问性</h5>
                            <p class="card-text">符合WCAG标准，支持键盘导航和屏幕阅读器</p>
                            <button class="btn btn-primary-financial" onclick="showFeatureDemo('accessibility')">查看演示</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 组件演示 -->
            <div class="row mb-4" id="demo">
                <div class="col-12">
                    <h2 class="mb-4">🎯 组件演示</h2>
                </div>
            </div>

            <!-- 按钮演示 -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card card-financial">
                        <div class="card-body">
                            <h5 class="card-title">按钮系统</h5>
                            <p class="card-text">专业的金融主题按钮，支持多种颜色和状态</p>
                            <div class="d-flex flex-wrap gap-2">
                                <button class="btn btn-primary-financial">主要按钮</button>
                                <button class="btn btn-success-financial">成功按钮</button>
                                <button class="btn btn-warning-financial">警告按钮</button>
                                <button class="btn btn-danger-financial">危险按钮</button>
                                <button class="btn btn-primary-financial btn-sm">小按钮</button>
                                <button class="btn btn-success-financial btn-lg">大按钮</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 数据表格演示 -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card card-financial">
                        <div class="card-body">
                            <h5 class="card-title">数据表格</h5>
                            <p class="card-text">移动端优化的数据表格，支持横向滚动</p>
                            <div class="table-responsive">
                                <table class="table table-financial">
                                    <thead>
                                        <tr>
                                            <th>股票代码</th>
                                            <th>股票名称</th>
                                            <th>当前价格</th>
                                            <th>涨跌幅</th>
                                            <th>成交量</th>
                                            <th>市值</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr>
                                            <td>000001</td>
                                            <td>平安银行</td>
                                            <td>12.34</td>
                                            <td class="text-success">+2.45%</td>
                                            <td>1,234,567</td>
                                            <td>2,345亿</td>
                                        </tr>
                                        <tr>
                                            <td>000002</td>
                                            <td>万科A</td>
                                            <td>23.45</td>
                                            <td class="text-danger">-1.23%</td>
                                            <td>987,654</td>
                                            <td>2,567亿</td>
                                        </tr>
                                        <tr>
                                            <td>600036</td>
                                            <td>招商银行</td>
                                            <td>45.67</td>
                                            <td class="text-success">+0.89%</td>
                                            <td>2,345,678</td>
                                            <td>1,234亿</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 统计数据 -->
            <div class="row mb-4">
                <div class="col-12">
                    <h5 class="mb-3">📊 改造统计</h5>
                </div>
            </div>

            <div class="row g-3 g-md-4 mb-5">
                <div class="col-6 col-md-3">
                    <div class="card card-financial text-center">
                        <div class="card-body">
                            <h3 class="text-primary number-display animate-pulse">2</h3>
                            <p class="card-text">CSS文件</p>
                        </div>
                    </div>
                </div>
                <div class="col-6 col-md-3">
                    <div class="card card-financial text-center">
                        <div class="card-body">
                            <h3 class="text-success number-display animate-pulse">500+</h3>
                            <p class="card-text">CSS规则</p>
                        </div>
                    </div>
                </div>
                <div class="col-6 col-md-3">
                    <div class="card card-financial text-center">
                        <div class="card-body">
                            <h3 class="text-warning number-display animate-pulse">20+</h3>
                            <p class="card-text">组件样式</p>
                        </div>
                    </div>
                </div>
                <div class="col-6 col-md-3">
                    <div class="card card-financial text-center">
                        <div class="card-body">
                            <h3 class="text-info number-display animate-pulse">100%</h3>
                            <p class="card-text">完成度</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 技术特点 -->
            <div class="row mb-4">
                <div class="col-12">
                    <h5 class="mb-3">🔧 技术特点</h5>
                </div>
            </div>

            <div class="row g-3 g-md-4">
                <div class="col-12 col-md-4">
                    <div class="card card-financial h-100">
                        <div class="card-body">
                            <h6 class="card-title">🎨 设计系统</h6>
                            <p class="card-text">完整的CSS变量系统，统一的设计令牌，专业的金融色彩搭配</p>
                        </div>
                    </div>
                </div>
                <div class="col-12 col-md-4">
                    <div class="card card-financial h-100">
                        <div class="card-body">
                            <h6 class="card-title">📱 响应式设计</h6>
                            <p class="card-text">从320px到1200px+的完整响应式支持，移动端优先的设计理念</p>
                        </div>
                    </div>
                </div>
                <div class="col-12 col-md-4">
                    <div class="card card-financial h-100">
                        <div class="card-body">
                            <h6 class="card-title">⚡ 性能优化</h6>
                            <p class="card-text">CSS优化、动画性能优化、减少重绘和回流，提升用户体验</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    
    <script>
        // 滚动到指定区域
        function scrollToSection(sectionId) {
            const element = document.getElementById(sectionId);
            if (element) {
                element.scrollIntoView({ behavior: 'smooth' });
            }
        }

        // 功能演示
        function showFeatureDemo(feature) {
            const messages = {
                'theme': '🎨 专业金融主题已应用！注意观察导航栏渐变、卡片阴影、按钮样式等设计元素。',
                'responsive': '📱 请尝试调整浏览器窗口大小，或在移动设备上查看响应式效果。',
                'animation': '✨ 请将鼠标悬停在卡片和按钮上，体验微交互动画效果。',
                'accessibility': '♿ 请尝试使用Tab键进行键盘导航，体验可访问性优化。'
            };
            
            alert(messages[feature] || '功能演示');
        }

        // 页面加载完成后的初始化
        document.addEventListener('DOMContentLoaded', function() {
            console.log('🎨 UI专业化改造演示页面已加载');
            
            // 添加页面加载动画
            const cards = document.querySelectorAll('.metric-card-enhanced');
            cards.forEach((card, index) => {
                setTimeout(() => {
                    card.style.opacity = '0';
                    card.style.transform = 'translateY(30px)';
                    card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                    
                    setTimeout(() => {
                        card.style.opacity = '1';
                        card.style.transform = 'translateY(0)';
                    }, 100);
                }, index * 100);
            });
        });

        // 卡片点击统计
        let clickCount = 0;
        document.querySelectorAll('.metric-card-enhanced').forEach(card => {
            card.addEventListener('click', function() {
                clickCount++;
                console.log(`卡片点击次数: ${clickCount}`);
            });
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """首页"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'message': 'UI专业化改造演示服务运行正常',
        'features': [
            '专业金融主题系统',
            '移动端响应式设计', 
            '微交互动画效果',
            '可访问性优化'
        ]
    })

if __name__ == '__main__':
    print("🎨 启动UI专业化改造演示服务...")
    print("📱 访问地址: http://localhost:5002")
    print("🔍 健康检查: http://localhost:5002/health")
    print("✨ 展示全新的专业金融主题界面")
    
    app.run(host='0.0.0.0', port=5002, debug=True) 