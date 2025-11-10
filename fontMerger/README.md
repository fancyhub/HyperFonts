# 字体合并工具

一个使用Python和fonttools库开发的字体合并工具，支持通过UI界面选择和合并多个字体文件。

## 环境搭建

1. 创建虚拟环境：
```bash
python -m venv venv
```

2. 激活虚拟环境：
   - Windows:
   ```bash
   venv\Scripts\activate
   ```
   - macOS/Linux:
   ```bash
source venv/bin/activate
   ```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

## 使用方法

1. 运行程序：
```bash
python font_merger.py
```

2. 点击"选择字体文件"按钮，选择要合并的多个字体文件

3. 点击"合并字体"按钮，选择保存路径并开始合并

4. 等待合并完成，会显示成功提示

## 注意事项

- 合并字体可能会导致某些特殊字符或字形出现问题
- 建议先合并少量字体进行测试
- 较大的字体文件可能需要较长时间合并