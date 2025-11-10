import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout, 
    QWidget, QListWidget, QListWidgetItem, QLabel, QMessageBox, QProgressBar, 
    QDoubleSpinBox, QGroupBox, QGridLayout, QCheckBox, QLineEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from fontTools.ttLib import TTFont
from fontTools.misc.transform import Transform
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen

class FontMergeThread(QThread):
    progress_updated = pyqtSignal(int)
    merge_completed = pyqtSignal(str)
    merge_error = pyqtSignal(str)
    
    def __init__(self, font_paths, output_path, font_scale_config=None, final_font_config=None):
        super().__init__()
        self.font_paths = font_paths
        self.output_path = output_path
        self.font_scale_config = font_scale_config or {}
        self.final_font_config = final_font_config or {}
        
    def run(self):
        try:
            # 加载第一个字体作为基础字体
            base_font = TTFont(self.font_paths[0])
            
            # 获取基础字体的EM大小
            base_units_per_em = self.get_units_per_em(base_font)
            
            # 合并其他字体
            total_fonts = len(self.font_paths)
            for i, font_path in enumerate(self.font_paths[1:], 1):
                try:
                    # 计算进度
                    progress = int((i / total_fonts) * 100)
                    self.progress_updated.emit(progress)
                    
                    # 加载要合并的字体
                    merge_font = TTFont(font_path)
                    
                    # 检查是否需要单独缩放此字体
                    font_basename = os.path.basename(font_path)
                    if font_basename in self.font_scale_config:
                        scale_config = self.font_scale_config[font_basename]
                        if scale_config.get('enabled', False):
                            target_height = scale_config.get('target_height', base_units_per_em)
                            current_units_per_em = self.get_units_per_em(merge_font)
                            if current_units_per_em != 0:
                                # 计算缩放比例
                                scale_factor = target_height / current_units_per_em
                                if scale_factor != 1.0:
                                    self.scale_font_glyphs(merge_font, scale_factor)
                    
                    # 合并字体数据
                    self.merge_font_data(base_font, merge_font)
                    
                except Exception as e:
                    self.merge_error.emit(f"合并字体 '{os.path.basename(font_path)}' 时出错: {str(e)}")
                    return
            
            # 设置最终字体配置
            if self.final_font_config:
                self.apply_final_font_config(base_font)
            
            # 最后检查并修复字体表的一致性
            self.finalize_font_tables(base_font)
            
            # 保存合并后的字体
            base_font.save(self.output_path)
            self.progress_updated.emit(100)
            self.merge_completed.emit(self.output_path)
            
        except Exception as e:
            self.merge_error.emit(f"处理过程中出错: {str(e)}")
    
    def get_units_per_em(self, font):
        # 获取字体的EM大小（通常在head表中）
        if 'head' in font:
            return font['head'].unitsPerEm
        return 1000  # 默认值
    
    def scale_font_glyphs(self, font, scale_factor):
        # 缩放字体的所有字形和相关表
        try:
            # 1. 缩放glyf表中的字形
            if 'glyf' in font:
                glyf_table = font['glyf']
                
                # 为每个字形创建一个新的缩放后的字形
                for glyph_name in glyf_table.glyphOrder:
                    glyph = glyf_table[glyph_name]
                    if glyph is not None and hasattr(glyph, 'coordinates'):
                        # 创建一个新的字形来存储缩放后的坐标
                        scaled_glyph = glyf_table[glyph_name].copy()
                        
                        # 缩放坐标
                        if scaled_glyph.coordinates:
                            scaled_glyph.coordinates = [
                                (x * scale_factor, y * scale_factor) 
                                for x, y in scaled_glyph.coordinates
                            ]
                        
                        # 更新字形边界框
                        if hasattr(scaled_glyph, 'xMin') and scaled_glyph.xMin is not None:
                            scaled_glyph.xMin = int(scaled_glyph.xMin * scale_factor)
                        if hasattr(scaled_glyph, 'yMin') and scaled_glyph.yMin is not None:
                            scaled_glyph.yMin = int(scaled_glyph.yMin * scale_factor)
                        if hasattr(scaled_glyph, 'xMax') and scaled_glyph.xMax is not None:
                            scaled_glyph.xMax = int(scaled_glyph.xMax * scale_factor)
                        if hasattr(scaled_glyph, 'yMax') and scaled_glyph.yMax is not None:
                            scaled_glyph.yMax = int(scaled_glyph.yMax * scale_factor)
                        
                        # 替换原始字形
                        glyf_table[glyph_name] = scaled_glyph
            
            # 2. 缩放hmtx表中的水平度量
            if 'hmtx' in font:
                hmtx_table = font['hmtx']
                metrics = {}
                
                for glyph_name, (width, lsb) in hmtx_table.metrics.items():
                    # 缩放宽度和左基线
                    metrics[glyph_name] = (int(width * scale_factor), int(lsb * scale_factor))
                
                # 替换原始度量
                hmtx_table.metrics = metrics
            
            # 3. 缩放vmtx表中的垂直度量（如果存在）
            if 'vmtx' in font:
                vmtx_table = font['vmtx']
                metrics = {}
                
                for glyph_name, (height, tsb) in vmtx_table.metrics.items():
                    # 缩放高度和顶基线
                    metrics[glyph_name] = (int(height * scale_factor), int(tsb * scale_factor))
                
                # 替换原始度量
                vmtx_table.metrics = metrics
            
            # 4. 更新head表中的unitsPerEm
            if 'head' in font:
                font['head'].unitsPerEm = int(font['head'].unitsPerEm * scale_factor)
            
            # 5. 更新hhea表中的相关值
            if 'hhea' in font:
                hhea = font['hhea']
                hhea.ascent = int(hhea.ascent * scale_factor)
                hhea.descent = int(hhea.descent * scale_factor)
                hhea.lineGap = int(hhea.lineGap * scale_factor)
                hhea.advanceWidthMax = int(hhea.advanceWidthMax * scale_factor)
            
            # 6. 更新OS/2表中的相关值
            if 'OS/2' in font:
                os2 = font['OS/2']
                if hasattr(os2, 'sTypoAscender'):
                    os2.sTypoAscender = int(os2.sTypoAscender * scale_factor)
                if hasattr(os2, 'sTypoDescender'):
                    os2.sTypoDescender = int(os2.sTypoDescender * scale_factor)
                if hasattr(os2, 'usWinAscent'):
                    os2.usWinAscent = int(os2.usWinAscent * scale_factor)
                if hasattr(os2, 'usWinDescent'):
                    os2.usWinDescent = int(os2.usWinDescent * scale_factor)
            
        except Exception as e:
            print(f"警告: 缩放字体时出错: {str(e)}")
    
    def merge_font_data(self, base_font, merge_font):
        # 1. 首先合并字形表
        self.merge_glyphs(base_font, merge_font)
        
        # 2. 合并水平度量表
        self.merge_hmtx(base_font, merge_font)
        
        # 3. 合并垂直度量表（如果存在）
        if 'vmtx' in base_font and 'vmtx' in merge_font:
            self.merge_vmtx(base_font, merge_font)
        
        # 4. 更新maxp表
        self.update_maxp_table(base_font)
        
        # 5. 合并cmap表
        self.merge_cmaps(base_font, merge_font)
        
        # 6. 合并OS/2表（重要的字体属性表）
        if 'OS/2' in base_font and 'OS/2' in merge_font:
            self.merge_os2_table(base_font, merge_font)
        
        # 7. 合并名称表
        self.merge_name_table(base_font, merge_font)
        
    def merge_glyphs(self, base_font, merge_font):
        # 获取基础字体和要合并字体的glyf表
        base_glyf = base_font['glyf']
        merge_glyf = merge_font['glyf']
        
        # 合并字形数据
        for glyph_name in merge_glyf.glyphOrder:
            if glyph_name not in base_glyf.glyphOrder:
                try:
                    # 如果基础字体中没有这个字形，则添加
                    base_glyf[glyph_name] = merge_glyf[glyph_name]
                except Exception as e:
                    # 某些特殊字形可能无法直接复制，记录但继续处理
                    print(f"警告: 无法合并字形 '{glyph_name}': {str(e)}")
    
    def merge_hmtx(self, base_font, merge_font):
        # 获取基础字体和要合并字体的hmtx表
        base_hmtx = base_font['hmtx']
        merge_hmtx = merge_font['hmtx']
        
        # 获取基础字体当前的glyph数量
        base_glyph_order = base_font.getGlyphOrder()
        
        # 合并hmtx数据
        for glyph_name in merge_font.getGlyphOrder():
            if glyph_name not in base_glyph_order:
                try:
                    # 获取该字形的水平度量
                    width, lsb = merge_hmtx[glyph_name]
                    # 添加到基础字体的hmtx表
                    base_hmtx[glyph_name] = (width, lsb)
                except Exception:
                    # 如果获取度量失败，使用默认值
                    base_hmtx[glyph_name] = (0, 0)
    
    def merge_vmtx(self, base_font, merge_font):
        # 获取基础字体和要合并字体的vmtx表
        base_vmtx = base_font['vmtx']
        merge_vmtx = merge_font['vmtx']
        
        # 获取基础字体当前的glyph数量
        base_glyph_order = base_font.getGlyphOrder()
        
        # 合并vmtx数据
        for glyph_name in merge_font.getGlyphOrder():
            if glyph_name not in base_glyph_order:
                try:
                    # 获取该字形的垂直度量
                    height, tsb = merge_vmtx[glyph_name]
                    # 添加到基础字体的vmtx表
                    base_vmtx[glyph_name] = (height, tsb)
                except Exception:
                    # 如果获取度量失败，使用默认值
                    base_vmtx[glyph_name] = (0, 0)
    
    def update_maxp_table(self, base_font):
        # 更新maxp表中的glyph数量
        if 'maxp' in base_font:
            base_font['maxp'].numGlyphs = len(base_font.getGlyphOrder())
    
    def merge_cmaps(self, base_font, merge_font):
        # 获取基础字体和要合并字体的cmap表
        base_cmap = base_font['cmap']
        merge_cmap = merge_font['cmap']
        
        # 合并字符映射
        for table in merge_cmap.tables:
            cmap_table = table.cmap
            for code, glyph_name in cmap_table.items():
                # 如果这个编码在基础字体中不存在，则添加
                found = False
                for base_table in base_cmap.tables:
                    if code in base_table.cmap:
                        found = True
                        break
                if not found:
                    # 添加到第一个cmap表中
                    base_cmap.tables[0].cmap[code] = glyph_name
    
    def merge_os2_table(self, base_font, merge_font):
        # 这里我们保留基础字体的OS/2表，但更新一些重要字段
        base_os2 = base_font['OS/2']
        merge_os2 = merge_font['OS/2']
        
        # 更新Unicode字符范围信息
        # 这里简化处理，保留基础字体的值
        pass
    
    def merge_name_table(self, base_font, merge_font):
        # 获取基础字体和要合并字体的name表
        base_name = base_font['name']
        merge_name = merge_font['name']
        
        # 合并名称记录
        name_ids = {record.nameID for record in base_name.names}
        for record in merge_name.names:
            if record.nameID not in name_ids:
                base_name.names.append(record)
    
    def finalize_font_tables(self, base_font):
        # 这个方法在所有字体合并完成后调用，用于确保所有表的一致性
        try:
            # 更新glyf顺序
            new_glyph_order = base_font.getGlyphOrder()
            
            # 确保hmtx表有所有字形的度量
            if 'hmtx' in base_font:
                hmtx = base_font['hmtx']
                for glyph_name in new_glyph_order:
                    if glyph_name not in hmtx.metrics:
                        hmtx[glyph_name] = (0, 0)
            
            # 确保maxp表正确
            self.update_maxp_table(base_font)
            
            # 尝试使用fontTools的表验证功能
            temp_path = os.path.join(os.path.dirname(self.output_path), 'temp_font.ttf')
            base_font.save(temp_path)
            # 重新加载验证
            temp_font = TTFont(temp_path)
            temp_font.close()
            os.remove(temp_path)
            
        except Exception as e:
            print(f"警告: 最终验证字体表时出错，但仍尝试保存: {str(e)}")

    def apply_final_font_config(self, font):        
        # 应用最终字体配置
        try:
            # 设置字体名称相关信息
            if 'name' in font and 'font_name' in self.final_font_config:
                name_table = font['name']
                font_name = self.final_font_config['font_name']
                family_name = self.final_font_config.get('family_name', font_name)
                style_name = self.final_font_config.get('style_name', '')
                version = self.final_font_config.get('version', 'Version 1.000')
                
                # 移除现有的名称记录
                # name_table.names = []
                
                # 添加新的名称记录
                # 英文名称记录
                name_table.setName(font_name, 4, 3, 1, 1033)  # 全名
                name_table.setName(family_name, 1, 3, 1, 1033)  # 字体系列
                name_table.setName(style_name, 2, 3, 1, 1033)  # 字体样式
                name_table.setName(version, 5, 3, 1, 1033)  # 版本
                
                # 中文名称记录
                name_table.setName(font_name, 4, 3, 1, 2052)  # 全名
                name_table.setName(family_name, 1, 3, 1, 2052)  # 字体系列
                name_table.setName(style_name, 2, 3, 1, 2052)  # 字体样式
                name_table.setName(version, 5, 3, 1, 2052)  # 版本
            
        except Exception as e:
            print(f"警告: 设置最终字体配置时出错: {str(e)}")

class FontMergerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.font_paths = []
        self.font_scale_widgets = {}
        self.font_scale_config = {}
        self.init_ui()
        
    def init_ui(self):
        # 设置窗口标题和大小
        self.setWindowTitle('字体合并工具')
        self.setGeometry(100, 100, 750, 600)  # 增加窗口宽度和高度以容纳新控件
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建选择字体按钮
        select_fonts_btn = QPushButton('选择字体文件')
        select_fonts_btn.clicked.connect(self.select_font_files)
        main_layout.addWidget(select_fonts_btn)
        
        # 创建字体列表显示区域
        self.font_list = QListWidget()
        main_layout.addWidget(QLabel('已选择的字体文件:(后面的字体会覆盖前面的相同字形)'))
        main_layout.addWidget(self.font_list)
        
        # 创建字体单独缩放选项区域
        scale_group = QGroupBox('字体单独缩放配置')
        scale_layout = QVBoxLayout()
        self.scale_config_widget = QWidget()
        self.scale_config_layout = QVBoxLayout(self.scale_config_widget)
        self.scale_config_layout.addWidget(QLabel('注: 选择需要单独缩放的字体并设置目标高度'))
        scale_layout.addWidget(self.scale_config_widget)
        scale_group.setLayout(scale_layout)
        main_layout.addWidget(scale_group)
        
        # 创建最终字体配置区域
        final_config_group = QGroupBox('最终字体配置')
        final_config_layout = QGridLayout()
        
        # 字体名称
        final_config_layout.addWidget(QLabel('字体全名:'), 0, 0)
        self.font_name_edit = QLineEdit()
        self.font_name_edit.setPlaceholderText('例如: MyMergedFont')
        final_config_layout.addWidget(self.font_name_edit, 0, 1)
        
        # 字体系列
        final_config_layout.addWidget(QLabel('字体系列:'), 1, 0)
        self.family_name_edit = QLineEdit()
        self.family_name_edit.setPlaceholderText('例如: MyMergedFont')
        final_config_layout.addWidget(self.family_name_edit, 1, 1)
        
        # 字体样式
        final_config_layout.addWidget(QLabel('字体样式:'), 2, 0)
        self.style_name_edit = QLineEdit()
        self.style_name_edit.setPlaceholderText('例如: Regular')
        final_config_layout.addWidget(self.style_name_edit, 2, 1)
        
        # 字体版本
        final_config_layout.addWidget(QLabel('字体版本:'), 3, 0)
        self.version_edit = QLineEdit('Version 1.000')
        final_config_layout.addWidget(self.version_edit, 3, 1)
        
        final_config_group.setLayout(final_config_layout)
        main_layout.addWidget(final_config_group)
        
        # 创建合并按钮
        merge_btn = QPushButton('合并字体')
        merge_btn.clicked.connect(self.merge_fonts)
        main_layout.addWidget(merge_btn)
        
        # 创建进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
    def select_font_files(self):
        # 打开文件对话框选择字体文件
        options = QFileDialog.Options()
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择字体文件", "", "字体文件 (*.ttf *.otf)", options=options
        )
        
        # 添加选中的文件到列表
        if files:
            self.font_paths = files
            self.update_font_list()
            self.update_scale_config_widgets()
    
    def update_font_list(self):
        # 清空并更新字体列表
        self.font_list.clear()
        for font_path in self.font_paths:
            item = QListWidgetItem(os.path.basename(font_path))
            item.setData(Qt.UserRole, font_path)
            self.font_list.addItem(item)
    
    def update_scale_config_widgets(self):
        # 清空现有控件
        while self.scale_config_layout.count() > 1:  # 保留第一个标签
            item = self.scale_config_layout.takeAt(1)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # 清空配置字典
        self.font_scale_config.clear()
        
        # 为每个字体创建缩放配置控件
        for font_path in self.font_paths:
            font_basename = os.path.basename(font_path)
            
            # 创建水平布局
            layout = QHBoxLayout()
            
            # 复选框
            checkbox = QCheckBox(font_basename)
            checkbox.stateChanged.connect(lambda state, fp=font_path: self.toggle_font_scale(state, fp))
            
            # 缩放高度输入框
            spinbox = QDoubleSpinBox()
            spinbox.setRange(10, 2048)
            spinbox.setValue(1000)  # 默认值
            spinbox.setSuffix(' 单位')
            spinbox.setEnabled(False)
            
            # 存储控件引用
            self.font_scale_widgets[font_basename] = (checkbox, spinbox)
            
            # 添加到布局
            layout.addWidget(checkbox)
            layout.addWidget(spinbox)
            layout.addStretch()
            
            # 添加到配置区域
            self.scale_config_layout.addLayout(layout)
    
    def toggle_font_scale(self, state, font_path):
        font_basename = os.path.basename(font_path)
        checkbox, spinbox = self.font_scale_widgets[font_basename]
        
        # 启用或禁用输入框
        spinbox.setEnabled(state == Qt.Checked)
        
        # 更新配置
        if state == Qt.Checked:
            self.font_scale_config[font_basename] = {
                'enabled': True,
                'target_height': spinbox.value()
            }
            spinbox.valueChanged.connect(lambda value, fp=font_path: self.update_font_scale_value(value, fp))
        else:
            if font_basename in self.font_scale_config:
                del self.font_scale_config[font_basename]
    
    def update_font_scale_value(self, value, font_path):
        font_basename = os.path.basename(font_path)
        if font_basename in self.font_scale_config:
            self.font_scale_config[font_basename]['target_height'] = value
    
    def merge_fonts(self):
        # 检查是否选择了字体文件
        if not self.font_paths:
            QMessageBox.warning(self, "警告", "请先选择要合并的字体文件")
            return
        
        # 选择输出文件路径
        options = QFileDialog.Options()
        output_path, _ = QFileDialog.getSaveFileName(
            self, "保存合并后的字体", "merged_font.ttf", "TrueType字体 (*.ttf);;OpenType字体 (*.otf)", options=options
        )
        
        if output_path:
            # 收集最终字体配置
            final_font_config = {}
            if self.font_name_edit.text().strip():
                final_font_config['font_name'] = self.font_name_edit.text().strip()
                final_font_config['family_name'] = self.family_name_edit.text().strip() or self.font_name_edit.text().strip()
                final_font_config['style_name'] = self.style_name_edit.text().strip()
                final_font_config['version'] = self.version_edit.text().strip() or 'Version 1.000'
            
            # 创建并启动合并线程
            self.merge_thread = FontMergeThread(
                self.font_paths, 
                output_path, 
                self.font_scale_config, 
                final_font_config
            )
            self.merge_thread.progress_updated.connect(self.update_progress)
            self.merge_thread.merge_completed.connect(self.merge_finished)
            self.merge_thread.merge_error.connect(self.merge_failed)
            self.merge_thread.start()
    
    def update_progress(self, value):
        # 更新进度条
        self.progress_bar.setValue(value)
    
    def merge_finished(self, output_path):
        # 合并完成后的处理
        QMessageBox.information(self, "成功", f"字体合并成功！\n保存路径: {output_path}")
        self.progress_bar.setValue(0)
    
    def merge_failed(self, error_message):
        # 合并失败后的处理
        QMessageBox.critical(self, "错误", f"字体合并失败！\n错误信息: {error_message}")
        print(f"错误详情: {error_message}")  # 打印错误信息到控制台，便于调试
        self.progress_bar.setValue(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FontMergerApp()
    window.show()
    sys.exit(app.exec_())