export type MockEvent = {
  id: number | string;
  text: string;
  start: string; // ISO datetime
  end: string;   // ISO datetime
  backColor?: string;
  participants?: string[]; // array of user ids (e.g. ["u1","u2"])
  ownerId?: string;
  tasks?: Task[]; // Added tasks array to align with EventItem type
};

export type Task = {
  id: string;
  title: string;
  description: string;
  assignees: string[];
  links: { id: string; url: string; title: string }[];
  startDate?: string;
  endDate?: string;
  columnId: string;
  eventId?: string;
};

export const mockEvents: MockEvent[] = [
  {
    id: 1,
    text: "Event 1",
    start: "2026-07-06T10:30:00",
    end: "2026-07-06T13:00:00",
    participants: ["u1", "u3"],
    backColor: "#f1c232cc",
    ownerId: "u1",
    tasks: [
      {
        id: "task1",
        title: "Prepare presentation for Event 1",
        description: "Create slides for the main session",
        assignees: ["u1", "u3"],
        links: [
          { id: "link1", url: "https://docs.example.com/slides", title: "Slide Template" }
        ],
        startDate: "2026-07-06T15:30:00",
        endDate: "2026-07-06T17:30:00",
        columnId: "todo",
        eventId: "1"
      },
      {
        id: "task2",
        title: "Setup venue",
        description: "Arrange seating and equipment",
        assignees: ["u3"],
        links: [],
        startDate: "2026-07-06T07:30:00",
        endDate: "2026-07-06T10:30:00",
        columnId: "todo",
        eventId: "1"
      }
    ]
  },
  {
    id: 2,
    text: "Event 2",
    start: "2026-07-07T09:30:00",
    end: "2026-07-07T11:30:00",
    backColor: "#6aa84fcc",
    participants: ["u2"],
    ownerId: "u2",
    tasks: [
      {
        id: "task3",
        title: "Send invitations",
        description: "Email invitations to participants",
        assignees: ["u2"],
        links: [
          { id: "link2", url: "https://invite.example.com", title: "Invitation Form" }
        ],
        startDate: "2026-07-06T00:00:00",
        endDate: "2026-07-07T23:59:59",
        columnId: "in-progress",
        eventId: "2"
      }
    ]
  },
  {
    id: 3,
    text: "Event 3",
    start: "2026-07-07T12:00:00",
    end: "2026-07-07T15:00:00",
    backColor: "#f1c232cc",
    participants: ["u2", "u4", "u5"],
    ownerId: "u4",
    tasks: [
      {
        id: "task4",
        title: "Cater food",
        description: "Organize lunch for attendees",
        assignees: ["u4", "u5"],
        links: [],
        startDate: "2026-07-07T00:00:00",
        endDate: "2026-07-07T23:59:59",
        columnId: "todo",
        eventId: "3"
      },
      {
        id: "task5",
        title: "Book guest speaker",
        description: "Confirm speaker availability",
        assignees: ["u2"],
        links: [
          { id: "link3", url: "https://speaker.example.com", title: "Speaker Profile" }
        ],
        startDate: "2026-07-06T00:00:00",
        endDate: "2026-07-07T23:59:59",
        columnId: "cancel",
        eventId: "3"
      }
    ]
  },
  {
    id: 4,
    text: "Event 4",
    start: "2026-07-05T11:30:00",
    end: "2026-07-05T14:30:00",
    backColor: "#cc4125cc",
    participants: ["u1", "u2", "u3", "u4"],
    ownerId: "u3",
    tasks: [
      {
        id: "task6",
        title: "Design posters",
        description: "Create promotional materials",
        assignees: ["u1", "u2"],
        links: [
          { id: "link4", url: "https://design.example.com", title: "Design Tool" },
          { id: "link5", url: "https://git.example.com", title: "Git Repository" }
        ],
        startDate: "2026-07-04T09:00:00",
        endDate: "2026-07-04T12:59:59",
        columnId: "in-progress",
        eventId: "4"
      },
      {
        id: "task7",
        title: "Test AV equipment",
        description: "Ensure audio-visual setup works",
        assignees: ["u3", "u4"],
        links: [],
        startDate: "2026-07-05T07:00:00",
        endDate: "2026-07-05T08:59:59",
        columnId: "in-progress",
        eventId: "4"
      }
    ]
  }
];