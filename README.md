# kb_assistant

## 项目架构
```text
kb_assistant/
|—— app/                                    源代码
|   |—— ingestion/
|       |—— build_index.py                      构建索引
|       |—— loader.py                       
|   |—— rag/                                知识检索
|       |—— vectorstore.py
|       |—— qa_graph.py                         QA 图
|       |—— prompts.py                          提示词
|   |—— config.py                           配置     
|   |—— deps.py
|   |—— router_graph.py                     顶级路由
|   |—— main.py                             主函数入口
|—— data/                                   数据
|   |——  docs/                                  语料库
|       |—— 公司考勤管理制度.docx
|       |—— 请假审批流程说明.docx
|       |—— 公司薪酬管理制度.pdf
|   |—— tests/                              测试代码
|   |—— ui/                                 前端界面
|       |—— streamlit_app.py
```

## 其他

例如，修改requirements.txt，添加
python-multipart==0.0.20
aiofiles==24.1.0
streamlit==1.40.2

使用如下命令更新
```bash
pip install -U -r requirements.txt
```



