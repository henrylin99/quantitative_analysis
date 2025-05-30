/**
 * 移动端优化JavaScript文件
 * 提供移动端特定的交互优化和功能增强
 */

// 移动端检测
const MobileDetector = {
    // 检测是否为移动设备
    isMobile: /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent),
    
    // 检测是否为平板
    isTablet: /iPad|Android/i.test(navigator.userAgent) && window.innerWidth >= 768,
    
    // 检测是否为iOS设备
    isIOS: /iPad|iPhone|iPod/.test(navigator.userAgent),
    
    // 检测是否为Android设备
    isAndroid: /Android/.test(navigator.userAgent),
    
    // 检测是否支持触摸
    isTouch: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
    
    // 获取屏幕尺寸类型
    getScreenSize: function() {
        const width = window.innerWidth;
        if (width < 576) return 'xs';
        if (width < 768) return 'sm';
        if (width < 992) return 'md';
        if (width < 1200) return 'lg';
        return 'xl';
    }
};

// 移动端优化管理器
const MobileOptimizer = {
    // 初始化
    init: function() {
        if (MobileDetector.isMobile || MobileDetector.isTablet) {
            this.optimizeNavigation();
            this.optimizeTables();
            this.optimizeModals();
            this.optimizeCharts();
            this.optimizeForms();
            this.optimizeTouch();
            this.preventZoom();
            this.handleOrientation();
        }
        
        // 监听窗口大小变化
        window.addEventListener('resize', this.handleResize.bind(this));
        
        // 监听方向变化
        window.addEventListener('orientationchange', this.handleOrientationChange.bind(this));
    },
    
    // 优化导航栏
    optimizeNavigation: function() {
        const navbar = document.querySelector('.navbar');
        const navbarCollapse = document.querySelector('.navbar-collapse');
        const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
        
        if (navbar && navbarCollapse) {
            // 点击导航链接后自动收起菜单
            navLinks.forEach(link => {
                link.addEventListener('click', function() {
                    if (navbarCollapse.classList.contains('show')) {
                        const bsCollapse = new bootstrap.Collapse(navbarCollapse);
                        bsCollapse.hide();
                    }
                });
            });
            
            // 点击外部区域收起菜单
            document.addEventListener('click', function(e) {
                if (!navbar.contains(e.target) && navbarCollapse.classList.contains('show')) {
                    const bsCollapse = new bootstrap.Collapse(navbarCollapse);
                    bsCollapse.hide();
                }
            });
        }
    },
    
    // 优化表格
    optimizeTables: function() {
        const tables = document.querySelectorAll('.table-responsive');
        
        tables.forEach(table => {
            // 启用触摸滚动
            table.style.webkitOverflowScrolling = 'touch';
            
            // 添加滚动指示器
            this.addScrollIndicator(table);
            
            // 优化表格行点击
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                row.style.cursor = 'pointer';
                row.addEventListener('touchstart', function() {
                    this.style.backgroundColor = 'rgba(0,0,0,0.05)';
                });
                row.addEventListener('touchend', function() {
                    setTimeout(() => {
                        this.style.backgroundColor = '';
                    }, 150);
                });
            });
        });
    },
    
    // 添加滚动指示器
    addScrollIndicator: function(container) {
        const indicator = document.createElement('div');
        indicator.className = 'scroll-indicator';
        indicator.innerHTML = '<i class="fas fa-arrows-alt-h"></i> 左右滑动查看更多';
        indicator.style.cssText = `
            position: absolute;
            top: 50%;
            right: 10px;
            transform: translateY(-50%);
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 12px;
            z-index: 10;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
        `;
        
        container.style.position = 'relative';
        container.appendChild(indicator);
        
        // 检查是否需要滚动
        const checkScroll = () => {
            const needsScroll = container.scrollWidth > container.clientWidth;
            indicator.style.opacity = needsScroll ? '1' : '0';
        };
        
        checkScroll();
        window.addEventListener('resize', checkScroll);
        
        // 滚动时隐藏指示器
        container.addEventListener('scroll', function() {
            indicator.style.opacity = '0';
        });
    },
    
    // 优化模态框
    optimizeModals: function() {
        const modals = document.querySelectorAll('.modal');
        
        modals.forEach(modal => {
            const dialog = modal.querySelector('.modal-dialog');
            if (dialog) {
                // 小屏幕全屏显示
                if (MobileDetector.getScreenSize() === 'xs') {
                    dialog.classList.add('modal-fullscreen');
                } else {
                    dialog.classList.add('modal-fullscreen-sm-down');
                }
                
                // 优化模态框滚动
                const body = modal.querySelector('.modal-body');
                if (body) {
                    body.style.webkitOverflowScrolling = 'touch';
                }
            }
        });
    },
    
    // 优化图表
    optimizeCharts: function() {
        const charts = document.querySelectorAll('.chart-container');
        
        charts.forEach(chart => {
            // 根据屏幕大小调整图表高度
            const screenSize = MobileDetector.getScreenSize();
            let height;
            
            switch (screenSize) {
                case 'xs':
                    height = '250px';
                    break;
                case 'sm':
                    height = '300px';
                    break;
                default:
                    height = '400px';
            }
            
            chart.style.height = height;
            
            // 如果是ECharts图表，重新调整大小
            if (typeof echarts !== 'undefined') {
                const chartInstance = echarts.getInstanceByDom(chart);
                if (chartInstance) {
                    setTimeout(() => chartInstance.resize(), 100);
                }
            }
        });
    },
    
    // 优化表单
    optimizeForms: function() {
        const inputs = document.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            // 防止iOS缩放
            if (MobileDetector.isIOS) {
                if (input.type !== 'file' && input.type !== 'range') {
                    input.style.fontSize = '16px';
                }
            }
            
            // 优化数字输入
            if (input.type === 'number') {
                input.setAttribute('inputmode', 'numeric');
                input.setAttribute('pattern', '[0-9]*');
            }
            
            // 优化邮箱输入
            if (input.type === 'email') {
                input.setAttribute('inputmode', 'email');
            }
            
            // 优化电话输入
            if (input.type === 'tel') {
                input.setAttribute('inputmode', 'tel');
            }
        });
    },
    
    // 优化触摸交互
    optimizeTouch: function() {
        // 增大触摸目标
        const touchTargets = document.querySelectorAll('.btn, .nav-link, .dropdown-item, .page-link, .list-group-item-action');
        
        touchTargets.forEach(target => {
            const computedStyle = window.getComputedStyle(target);
            const minHeight = parseInt(computedStyle.minHeight) || 0;
            
            if (minHeight < 44) {
                target.style.minHeight = '44px';
                target.style.display = 'flex';
                target.style.alignItems = 'center';
                target.style.justifyContent = 'center';
            }
        });
        
        // 优化触摸反馈
        document.addEventListener('touchstart', function(e) {
            const target = e.target.closest('.btn, .card, .list-group-item');
            if (target) {
                target.style.transform = 'scale(0.98)';
                target.style.transition = 'transform 0.1s';
            }
        }, {passive: true});
        
        document.addEventListener('touchend', function(e) {
            const target = e.target.closest('.btn, .card, .list-group-item');
            if (target) {
                setTimeout(() => {
                    target.style.transform = '';
                }, 100);
            }
        }, {passive: true});
    },
    
    // 防止缩放
    preventZoom: function() {
        if (MobileDetector.isIOS) {
            // 防止双击缩放
            let lastTouchEnd = 0;
            document.addEventListener('touchend', function(event) {
                const now = (new Date()).getTime();
                if (now - lastTouchEnd <= 300) {
                    event.preventDefault();
                }
                lastTouchEnd = now;
            }, false);
            
            // 防止手势缩放
            document.addEventListener('gesturestart', function(e) {
                e.preventDefault();
            });
            
            document.addEventListener('gesturechange', function(e) {
                e.preventDefault();
            });
            
            document.addEventListener('gestureend', function(e) {
                e.preventDefault();
            });
        }
    },
    
    // 处理方向变化
    handleOrientation: function() {
        // 横屏时的特殊处理
        const isLandscape = window.orientation === 90 || window.orientation === -90;
        
        if (isLandscape && MobileDetector.isMobile) {
            // 横屏时减小图表高度
            const charts = document.querySelectorAll('.chart-container');
            charts.forEach(chart => {
                chart.style.height = '200px';
            });
            
            // 横屏时减小导航栏高度
            const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
            navLinks.forEach(link => {
                link.style.padding = '0.5rem 1rem';
            });
        }
    },
    
    // 处理窗口大小变化
    handleResize: function() {
        clearTimeout(this.resizeTimeout);
        this.resizeTimeout = setTimeout(() => {
            this.optimizeCharts();
            this.optimizeModals();
            
            // 重新调整ECharts图表
            if (typeof echarts !== 'undefined') {
                const charts = document.querySelectorAll('.chart-container');
                charts.forEach(container => {
                    const chart = echarts.getInstanceByDom(container);
                    if (chart) {
                        chart.resize();
                    }
                });
            }
        }, 250);
    },
    
    // 处理方向变化
    handleOrientationChange: function() {
        setTimeout(() => {
            this.handleOrientation();
            this.handleResize();
        }, 500);
    }
};

// 移动端工具函数
const MobileUtils = {
    // 显示移动端友好的提示
    showMobileToast: function(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `mobile-toast mobile-toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#17a2b8'};
            color: white;
            padding: 12px 20px;
            border-radius: 25px;
            font-size: 14px;
            z-index: 9999;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            opacity: 0;
            transition: opacity 0.3s;
        `;
        
        document.body.appendChild(toast);
        
        // 显示动画
        setTimeout(() => {
            toast.style.opacity = '1';
        }, 10);
        
        // 自动隐藏
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 300);
        }, duration);
    },
    
    // 移动端加载指示器
    showMobileLoading: function(container) {
        const loading = document.createElement('div');
        loading.className = 'mobile-loading';
        loading.innerHTML = `
            <div class="mobile-spinner"></div>
            <div class="mobile-loading-text">加载中...</div>
        `;
        loading.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255,255,255,0.9);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 100;
        `;
        
        const spinner = loading.querySelector('.mobile-spinner');
        spinner.style.cssText = `
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #007bff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 10px;
        `;
        
        const text = loading.querySelector('.mobile-loading-text');
        text.style.cssText = `
            font-size: 14px;
            color: #666;
        `;
        
        // 添加旋转动画
        if (!document.querySelector('#mobile-spinner-style')) {
            const style = document.createElement('style');
            style.id = 'mobile-spinner-style';
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }
        
        container.style.position = 'relative';
        container.appendChild(loading);
        
        return loading;
    },
    
    // 隐藏移动端加载指示器
    hideMobileLoading: function(container) {
        const loading = container.querySelector('.mobile-loading');
        if (loading) {
            loading.remove();
        }
    },
    
    // 移动端确认对话框
    showMobileConfirm: function(message, callback) {
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            padding: 20px;
        `;
        
        const dialog = document.createElement('div');
        dialog.style.cssText = `
            background: white;
            border-radius: 12px;
            padding: 20px;
            max-width: 300px;
            width: 100%;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        `;
        
        dialog.innerHTML = `
            <div style="margin-bottom: 20px; font-size: 16px; line-height: 1.5;">${message}</div>
            <div style="display: flex; gap: 10px;">
                <button class="mobile-confirm-cancel" style="flex: 1; padding: 12px; border: 1px solid #ddd; background: white; border-radius: 8px; font-size: 14px;">取消</button>
                <button class="mobile-confirm-ok" style="flex: 1; padding: 12px; border: none; background: #007bff; color: white; border-radius: 8px; font-size: 14px;">确定</button>
            </div>
        `;
        
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        
        // 事件处理
        dialog.querySelector('.mobile-confirm-cancel').addEventListener('click', function() {
            document.body.removeChild(overlay);
            if (callback) callback(false);
        });
        
        dialog.querySelector('.mobile-confirm-ok').addEventListener('click', function() {
            document.body.removeChild(overlay);
            if (callback) callback(true);
        });
        
        // 点击外部关闭
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                document.body.removeChild(overlay);
                if (callback) callback(false);
            }
        });
    },
    
    // 获取安全区域
    getSafeArea: function() {
        const safeAreaTop = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--sat') || '0');
        const safeAreaBottom = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--sab') || '0');
        
        return {
            top: safeAreaTop,
            bottom: safeAreaBottom
        };
    }
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    MobileOptimizer.init();
    
    // 设置CSS变量用于安全区域
    if (MobileDetector.isIOS && 'CSS' in window && 'supports' in window.CSS) {
        if (window.CSS.supports('padding-top: env(safe-area-inset-top)')) {
            document.documentElement.style.setProperty('--sat', 'env(safe-area-inset-top)');
            document.documentElement.style.setProperty('--sab', 'env(safe-area-inset-bottom)');
        }
    }
});

// 导出到全局
window.MobileDetector = MobileDetector;
window.MobileOptimizer = MobileOptimizer;
window.MobileUtils = MobileUtils; 