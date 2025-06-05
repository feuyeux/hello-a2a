import asyncio
import datetime
import uuid

from a2a.types import (
    AgentCard,
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from utils.agent_card import get_agent_card

from service.server.adk_host_manager import task_still_open
from service.server.application_manager import ApplicationManager
from service.types import Conversation, Event


class InMemoryFakeAgentManager(ApplicationManager):
    """An implementation of memory based management with fake agent actions.

    This implements the interface of the ApplicationManager to plug into
    the AgentServer. This acts as the service contract that the Mesop app
    uses to send messages to the agent and provide information for the frontend.

    Used primarily for testing and demonstration purposes - simulates agent
    responses with predefined messages from a queue.
    """

    _conversations: list[Conversation]
    _messages: list[Message]
    _tasks: list[Task]
    _events: list[Event]
    _pending_message_ids: list[str]
    _next_message_idx: int
    _agents: list[AgentCard]

    def __init__(self):
        """Initialize the in-memory fake agent manager.
        Sets up empty collections for conversations, messages, tasks, and events.
        """
        print("[InMemoryFakeAgentManager] 🚀 Initializing fake agent manager")
        self._conversations = []
        self._messages = []
        self._tasks = []
        self._events = []
        self._pending_message_ids = []
        self._next_message_idx = 0
        self._agents = []
        self._task_map = {}
        print("[InMemoryFakeAgentManager] ✅ Initialization complete")

    async def create_conversation(self) -> Conversation:
        """Create a new conversation for testing purposes.
        Generates a unique conversation ID and marks it as active.

        Returns:
            New Conversation object with generated ID
        """
        conversation_id = str(uuid.uuid4())
        print(
            f"[InMemoryFakeAgentManager] 💬 Creating new conversation: {conversation_id}")

        c = Conversation(conversation_id=conversation_id, is_active=True)
        self._conversations.append(c)

        print("[InMemoryFakeAgentManager] ✅ Conversation created successfully")
        print(
            f"[InMemoryFakeAgentManager] 📊 Total conversations: {len(self._conversations)}")
        return c

    def sanitize_message(self, message: Message) -> Message:
        """Sanitize and prepare message for processing.
        Handles task continuation logic for ongoing conversations.

        Flow:
        1. Find conversation by context ID
        2. Check if last message had an open task
        3. Attach task ID to current message if continuing

        Args:
            message: Input message to sanitize

        Returns:
            Sanitized message with appropriate task ID
        """
        print("[InMemoryFakeAgentManager] 🔧 Sanitizing message")
        print(f"[InMemoryFakeAgentManager] 🎯 Context ID: {message.contextId}")
        print(
            f"[InMemoryFakeAgentManager] 📋 Current Task ID: {message.taskId}")

        if message.contextId:
            conversation = self.get_conversation(message.contextId)
            print(
                f"[InMemoryFakeAgentManager] 💬 Found conversation: {conversation is not None}")
        else:
            conversation = None
            print("[InMemoryFakeAgentManager] ⚠️ No context ID provided")

        if not conversation:
            print(
                "[InMemoryFakeAgentManager] ✅ No conversation context, returning message as-is")
            return message

        # Check if the last event in the conversation was tied to a task.
        if conversation.messages:
            last_message = conversation.messages[-1]
            print(
                f"[InMemoryFakeAgentManager] 📄 Last message task ID: {last_message.taskId}")

            if last_message.taskId:
                # Find the task and check if it's still open
                task = next(
                    filter(
                        lambda x: x.id == last_message.taskId,
                        self._tasks,
                    ),
                    None,
                )

                if task:
                    is_open = task_still_open(task)
                    print(
                        f"[InMemoryFakeAgentManager] 📋 Task {task.id} is open: {is_open}")

                    if is_open:
                        print(
                            f"[InMemoryFakeAgentManager] 🔗 Continuing task: {last_message.taskId}")
                        message.taskId = last_message.taskId
                else:
                    print(
                        f"[InMemoryFakeAgentManager] ⚠️ Task not found: {last_message.taskId}")
        else:
            print("[InMemoryFakeAgentManager] 📭 No previous messages in conversation")

        print("[InMemoryFakeAgentManager] ✅ Message sanitization complete")
        return message

    async def process_message(self, message: Message, correlation_id: str | None = None):
        """Process an incoming message in the fake agent environment.
        This simulates the complete message processing flow for testing.

        Flow:
        1. Store message and mark as pending
        2. Add to conversation history
        3. Create UI event for message
        4. Create and process task
        5. Generate fake response after delay
        6. Complete task with artifacts

        Args:
            message: Input message to process
        """
        print("[InMemoryFakeAgentManager] 🎯 Processing message")
        print(f"[InMemoryFakeAgentManager] 🆔 Message ID: {message.messageId}")
        print(f"[InMemoryFakeAgentManager] 💬 Context ID: {message.contextId}")
        print(f"[InMemoryFakeAgentManager] 📋 Task ID: {message.taskId}")

        # Store the message
        self._messages.append(message)
        message_id = message.messageId
        context_id = message.contextId or ''
        task_id = message.taskId or ''

        if message_id:
            self._pending_message_ids.append(message_id)
            print(
                f"[InMemoryFakeAgentManager] ⏳ Added to pending messages: {message_id}")

        # Add to conversation
        conversation = self.get_conversation(context_id)
        if conversation:
            conversation.messages.append(message)
            print("[InMemoryFakeAgentManager] 💬 Added message to conversation")
        else:
            print("[InMemoryFakeAgentManager] ⚠️ No conversation found for context")

        # Create event for UI
        print("[InMemoryFakeAgentManager] 📢 Creating UI event for message")
        self._events.append(
            Event(
                id=str(uuid.uuid4()),
                actor='host',
                content=message,
                timestamp=datetime.datetime.utcnow().timestamp(),
            )
        )

        # Create task for processing
        print("[InMemoryFakeAgentManager] 📋 Creating processing task")
        task = Task(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(
                state=TaskState.submitted,
                message=message,
            ),
            history=[message],
        )

        if self._next_message_idx != 0:
            print("[InMemoryFakeAgentManager] 📝 Adding task to queue")
            self.add_task(task)

        # Simulate processing delay
        print(
            f"[InMemoryFakeAgentManager] ⏱️ Simulating processing delay: {self._next_message_idx}s")
        await asyncio.sleep(self._next_message_idx)

        # Generate fake response
        print("[InMemoryFakeAgentManager] 🤖 Generating fake response")
        response = self.next_message()

        if conversation:
            conversation.messages.append(response)
            print("[InMemoryFakeAgentManager] 💬 Added response to conversation")

        # Create event for response
        print("[InMemoryFakeAgentManager] 📢 Creating UI event for response")
        self._events.append(
            Event(
                id=str(uuid.uuid4()),
                actor='host',
                content=response,
                timestamp=datetime.datetime.utcnow().timestamp(),
            )
        )

        # Remove from pending
        if message_id in self._pending_message_ids:
            self._pending_message_ids.remove(message_id)
            print("[InMemoryFakeAgentManager] ✅ Removed from pending messages")

        # Complete the task
        if task:
            print("[InMemoryFakeAgentManager] 🏁 Completing task with artifacts")
            task.status.state = TaskState.completed
            task.artifacts = [
                Artifact(
                    name='response',
                    parts=response.parts,
                    artifactId=str(uuid.uuid4()),
                )
            ]
            if not task.history:
                task.history = [response]
            else:
                task.history.append(response)
            self.update_task(task)

        print("[InMemoryFakeAgentManager] ✅ Message processing complete")

    def add_task(self, task: Task):
        """Add a task to the fake task queue.

        Args:
            task: Task to add to the queue
        """
        print(f"[InMemoryFakeAgentManager] 📝 Adding task to queue: {task.id}")
        self._tasks.append(task)
        print(f"[InMemoryFakeAgentManager] 📊 Total tasks: {len(self._tasks)}")

    def update_task(self, task: Task):
        """Update an existing task in the queue.

        Args:
            task: Task with updated information
        """
        print(f"[InMemoryFakeAgentManager] 🔄 Updating task: {task.id}")

        for i, t in enumerate(self._tasks):
            if t.id == task.id:
                self._tasks[i] = task
                print(
                    f"[InMemoryFakeAgentManager] ✅ Task updated at index {i}")
                return

        print(
            f"[InMemoryFakeAgentManager] ⚠️ Task not found for update: {task.id}")

    def add_event(self, event: Event):
        """Add an event to the fake event queue.

        Args:
            event: Event to add to the queue
        """
        print(f"[InMemoryFakeAgentManager] 📢 Adding event: {event.id}")
        self._events.append(event)
        print(
            f"[InMemoryFakeAgentManager] 📊 Total events: {len(self._events)}")

    def next_message(self) -> Message:
        """Get the next fake message from the predefined queue.
        Cycles through messages in a round-robin fashion.

        Returns:
            Next message from the fake message queue
        """
        print("[InMemoryFakeAgentManager] 🎭 Getting next fake message")
        print(
            f"[InMemoryFakeAgentManager] 🔢 Current index: {self._next_message_idx}")

        message = _message_queue[self._next_message_idx]
        self._next_message_idx = (self._next_message_idx + 1) % len(
            _message_queue
        )

        print(
            f"[InMemoryFakeAgentManager] ✅ Returning fake message, next index: {self._next_message_idx}")
        return message

    def get_conversation(
        self, conversation_id: str | None
    ) -> Conversation | None:
        """Retrieve a conversation by its ID.

        Args:
            conversation_id: ID of the conversation to find

        Returns:
            Conversation object if found, None otherwise
        """
        if not conversation_id:
            print("[InMemoryFakeAgentManager] ⚠️ No conversation ID provided")
            return None

        print(
            f"[InMemoryFakeAgentManager] 🔍 Looking for conversation: {conversation_id}")

        conversation = next(
            filter(
                lambda c: c and c.conversation_id == conversation_id,
                self._conversations,
            ),
            None,
        )

        if conversation:
            print("[InMemoryFakeAgentManager] ✅ Found conversation")
        else:
            print("[InMemoryFakeAgentManager] ❌ Conversation not found")

        return conversation

    def get_pending_messages(self) -> list[tuple[str, str]]:
        """Get all currently pending messages with their status.
        Returns message IDs and their current processing status.

        Returns:
            List of tuples containing (message_id, status_text)
        """
        print("[InMemoryFakeAgentManager] 📋 Getting pending messages")
        print(
            f"[InMemoryFakeAgentManager] 📊 Pending count: {len(self._pending_message_ids)}")

        rval: list[tuple[str, str]] = []
        for message_id in self._pending_message_ids:
            print(
                f"[InMemoryFakeAgentManager] 🔍 Processing pending message: {message_id}")

            if message_id in self._task_map:
                task_id = self._task_map[message_id]
                print(
                    f"[InMemoryFakeAgentManager] 📋 Found task mapping: {task_id}")

                task = next(
                    filter(lambda x: x.id == task_id, self._tasks), None
                )

                if not task:
                    rval.append((message_id, ''))
                elif task.history and task.history[-1].parts:
                    if len(task.history) == 1:
                        rval.append((message_id, 'Working...'))
                    else:
                        part = task.history[-1].parts[0]
                        status_text = (
                            part.root.text
                            if part.root.kind == 'text'
                            else 'Working...'
                        )
                        rval.append((message_id, status_text))
                else:
                    rval.append((message_id, ''))
            else:
                rval.append((message_id, ''))

        # Note: Original code had an early return here, which seems like a bug
        # We'll return the full list instead
        return rval

    def register_agent(self, url):
        """Register a fake agent for testing purposes.
        Resolves agent card and adds to available agents list.

        Args:
            url: URL of the agent to register
        """
        print(f"[InMemoryFakeAgentManager] 🔗 Registering fake agent: {url}")

        try:
            agent_data = get_agent_card(url)
            if not agent_data.url:
                agent_data.url = url
                print(f"[InMemoryFakeAgentManager] 🔧 Set agent URL: {url}")

            self._agents.append(agent_data)
            print("[InMemoryFakeAgentManager] ✅ Agent registered successfully")
            print(
                f"[InMemoryFakeAgentManager] 🤖 Agent name: {agent_data.name}")
            print(
                f"[InMemoryFakeAgentManager] 📊 Total agents: {len(self._agents)}")

        except Exception as e:
            print(
                f"[InMemoryFakeAgentManager] ❌ Failed to register agent: {e!s}")
            raise

    @property
    def agents(self) -> list[AgentCard]:
        return self._agents

    @property
    def conversations(self) -> list[Conversation]:
        return self._conversations

    @property
    def tasks(self) -> list[Task]:
        return self._tasks

    @property
    def events(self) -> list[Event]:
        return []


_contextId = str(uuid.uuid4())

# This represents the precanned responses that will be returned in order.
# Extend this list to test more functionality of the UI
_message_queue: list[Message] = [
    Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text='Hello'))],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
    Message(
        role=Role.agent,
        parts=[
            Part(
                root=DataPart(
                    data={
                        'type': 'form',
                        'form': {
                            'type': 'object',
                            'properties': {
                                'name': {
                                    'type': 'string',
                                    'description': 'Enter your name',
                                    'title': 'Name',
                                },
                                'date': {
                                    'type': 'string',
                                    'format': 'date',
                                    'description': 'Birthday',
                                    'title': 'Birthday',
                                },
                            },
                            'required': ['date'],
                        },
                        'form_data': {
                            'name': 'John Smith',
                        },
                        'instructions': 'Please provide your birthday and name',
                    }
                )
            ),
        ],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
    Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text='I like cats'))],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
    Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text='And I like dogs'))],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
]
