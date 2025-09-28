# Dice Agent (Multi-Transport)

这个智能体示例可以掷不同大小的骰子并检查数字是否为质数

https://github.com/a2aproject/a2a-samples/tree/main/samples/java/agents/dice_agent_multi_transport

## 构建项目

- 首先构建服务器模块: `mvn clean install -DskipTests -pl server`
- 然后构建客户端模块: `mvn clean install -DskipTests -pl client`
- 最后构建整个项目: `mvn clean install -DskipTests`

## 运行 A2A 服务器智能体

```sh
cd server
# 如果遇到模型不存在的错误，请先检查 src/main/resources/application.properties 中的模型配置
mvn quarkus:dev
```

## 运行 A2A 客户端

### 使用 Maven (推荐)

```sh
cd client
# 使用默认消息运行
mvn exec:java

# 使用自定义消息运行
mvn exec:java -Dexec.args="--message \"你能掷一个 12 面的骰子并检查结果是否为素数吗?\""
```

### 使用 JBang (可选)

```sh
cd client
jbang src/main/java/com/samples/a2a/client/TestClientRunner.java --message "你能掷一个 12 面的骰子并检查结果是否为素数吗?"
```

### 使用批处理文件 (Windows)

```sh
cd client
run_client.bat
```

## 故障排除

1. **服务器启动失败**: 检查 Ollama 服务是否运行在 `localhost:11434`，并确认配置的模型是否存在
2. **客户端连接失败**: 确保服务器正在运行并监听端口 11000
3. **中文字符显示问题**: 在 Windows 上使用提供的批处理文件或确保终端支持 UTF-8 编码
