//
//  IdeaGraphView.swift
//  CortxApp
//
//  Interactive force-directed idea graph visualization.
//  Shows entities (People, Projects, Topics) as animated bubbles
//  with connection lines between co-occurring entities.
//

import SwiftUI
import Combine

// MARK: - Node Position Model

class GraphNodePosition: ObservableObject, Identifiable {
    let entity: IdeaGraphEntity
    @Published var position: CGPoint
    @Published var velocity: CGPoint = .zero
    @Published var isSelected: Bool = false

    var id: String { entity.id }

    init(entity: IdeaGraphEntity, position: CGPoint) {
        self.entity = entity
        self.position = position
    }

    var radius: CGFloat {
        let base: CGFloat = 28
        let mentionScale = CGFloat(min(entity.mention_count, 20))
        return base + mentionScale * 2.5
    }
}

// MARK: - Force Graph ViewModel

@MainActor
class IdeaGraphViewModel: ObservableObject {
    @Published var graphData: IdeaGraphResponse?
    @Published var nodes: [GraphNodePosition] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var selectedNode: GraphNodePosition?
    @Published var mentions: [IdeaGraphMention] = []
    @Published var mentionsLoading = false
    @Published var filterType: String? = nil

    private let api = APIClient()
    private var simulationTimer: Timer?

    func loadGraph(accessToken: String) async {
        isLoading = true
        errorMessage = nil

        do {
            let response = try await api.fetchIdeaGraph(
                accessToken: accessToken,
                entityType: filterType,
                minMentions: 1,
                limit: 100
            )
            self.graphData = response
            self.buildNodes(from: response, in: CGSize(width: 600, height: 600))
            self.startSimulation()
        } catch {
            self.errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    func loadMentions(entityID: String, accessToken: String) async {
        mentionsLoading = true
        do {
            mentions = try await api.fetchEntityMentions(entityID: entityID, accessToken: accessToken)
        } catch {
            mentions = []
        }
        mentionsLoading = false
    }

    private func buildNodes(from response: IdeaGraphResponse, in size: CGSize) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let count = response.nodes.count
        nodes = response.nodes.enumerated().map { index, entity in
            let angle = 2 * .pi * Double(index) / max(Double(count), 1.0)
            let spreadRadius = min(size.width, size.height) * 0.35
            let x = center.x + CGFloat(cos(angle)) * spreadRadius + CGFloat.random(in: -30...30)
            let y = center.y + CGFloat(sin(angle)) * spreadRadius + CGFloat.random(in: -30...30)
            return GraphNodePosition(entity: entity, position: CGPoint(x: x, y: y))
        }
    }

    func startSimulation() {
        simulationTimer?.invalidate()
        simulationTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor [self] in
                self.simulationStep()
            }
        }
        // Run for 4 seconds then stop
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { [weak self] in
            self?.simulationTimer?.invalidate()
        }
    }

    private func simulationStep() {
        guard let graph = graphData else { return }
        let center = CGPoint(x: 300, y: 300)
        let damping: CGFloat = 0.85
        let dt: CGFloat = 0.3

        // Build edge set for attraction
        var edgeSet: Set<String> = []
        for edge in graph.edges {
            edgeSet.insert("\(edge.source_entity_id)|\(edge.target_entity_id)")
            edgeSet.insert("\(edge.target_entity_id)|\(edge.source_entity_id)")
        }

        for i in 0..<nodes.count {
            var force = CGPoint.zero

            // Gravity towards center
            let dx = center.x - nodes[i].position.x
            let dy = center.y - nodes[i].position.y
            force.x += dx * 0.003
            force.y += dy * 0.003

            // Repulsion from other nodes
            for j in 0..<nodes.count where i != j {
                let rx = nodes[i].position.x - nodes[j].position.x
                let ry = nodes[i].position.y - nodes[j].position.y
                let dist = max(sqrt(rx * rx + ry * ry), 1)
                let repulsionForce: CGFloat = 3000.0 / (dist * dist)
                force.x += (rx / dist) * repulsionForce
                force.y += (ry / dist) * repulsionForce
            }

            // Attraction along edges
            for j in 0..<nodes.count where i != j {
                let key = "\(nodes[i].entity.id)|\(nodes[j].entity.id)"
                if edgeSet.contains(key) {
                    let ax = nodes[j].position.x - nodes[i].position.x
                    let ay = nodes[j].position.y - nodes[i].position.y
                    let dist = max(sqrt(ax * ax + ay * ay), 1)
                    let idealDist: CGFloat = 120
                    let attractForce = (dist - idealDist) * 0.008
                    force.x += (ax / dist) * attractForce
                    force.y += (ay / dist) * attractForce
                }
            }

            if !nodes[i].isSelected {
                nodes[i].velocity.x = (nodes[i].velocity.x + force.x * dt) * damping
                nodes[i].velocity.y = (nodes[i].velocity.y + force.y * dt) * damping
                nodes[i].position.x += nodes[i].velocity.x * dt
                nodes[i].position.y += nodes[i].velocity.y * dt
            }
        }
    }

    func selectNode(_ node: GraphNodePosition?) {
        for n in nodes {
            n.isSelected = false
        }
        selectedNode = node
        node?.isSelected = true
        mentions = []
    }
}

// MARK: - Entity Type Colors

extension Color {
    static func entityColor(for type: String) -> Color {
        switch type {
        case "person": return Color(red: 0.35, green: 0.62, blue: 0.95)
        case "project": return Color(red: 0.55, green: 0.85, blue: 0.35)
        case "topic": return Color(red: 0.95, green: 0.65, blue: 0.22)
        case "place": return Color(red: 0.82, green: 0.35, blue: 0.65)
        case "organization": return Color(red: 0.60, green: 0.45, blue: 0.90)
        default: return Color.gray
        }
    }
}

// MARK: - Graph View

struct IdeaGraphView: View {
    @ObservedObject var session: AppSessionViewModel
    let onClose: (() -> Void)?
    @StateObject private var vm = IdeaGraphViewModel()
    @Namespace private var filterNamespace
    @State private var viewportOffset: CGSize = .zero
    @State private var committedOffset: CGSize = .zero
    @State private var viewportScale: CGFloat = 1.0
    @State private var committedScale: CGFloat = 1.0
    @State private var reveal = false

    private let filterTypes = [
        ("All", nil as String?),
        ("People", "person"),
        ("Projects", "project"),
        ("Topics", "topic"),
        ("Places", "place"),
        ("Orgs", "organization"),
    ]

    init(session: AppSessionViewModel, onClose: (() -> Void)? = nil) {
        self.session = session
        self.onClose = onClose
    }

    var body: some View {
        ZStack {
            AppBackgroundView()

            ScrollView(showsIndicators: false) {
                VStack(spacing: 10) {
                    graphHeader
                    filterChips
                    graphCanvas
                }
                .padding(.bottom, vm.selectedNode == nil ? 14 : 120)
            }
            .opacity(reveal ? 1.0 : 0.0)
            .offset(y: reveal ? 0 : 12)
            .animation(.easeOut(duration: 0.35), value: reveal)
        }
        .safeAreaInset(edge: .bottom) {
            if let selected = vm.selectedNode {
                entityDetailPanel(selected)
                    .padding(.bottom, 6)
            }
        }
        .task {
            guard let token = session.accessToken else { return }
            await vm.loadGraph(accessToken: token)
        }
        .onAppear {
            reveal = true
        }
    }

    // MARK: - Header

    private var graphHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let onClose {
                    Button(action: onClose) {
                        Label("Dashboard", systemImage: "chevron.left")
                            .lineLimit(1)
                    }
                    .buttonStyle(LiquidSecondaryButtonStyle())
                }
                Spacer()
                headerActions
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Idea Graph")
                    .font(.system(size: 42, weight: .black, design: .rounded))
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                Text("Your thoughts, people, and projects — connected.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .layoutPriority(1)

            if let data = vm.graphData {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        graphStatBadge("\(data.total_entities)", label: "Entities", icon: "circle.grid.3x3.fill")
                        graphStatBadge("\(data.total_connections)", label: "Links", icon: "link")
                        graphStatBadge("Drag + pinch", label: "Explore", icon: "hand.draw")
                    }
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .padding(.bottom, 8)
    }

    private var headerActions: some View {
        HStack(spacing: 8) {
            Button {
                resetViewport(animated: true)
            } label: {
                Image(systemName: "view.3d")
                    .font(.body.weight(.semibold))
            }
            .buttonStyle(LiquidSecondaryButtonStyle())

            Button {
                Task {
                    guard let token = session.accessToken else { return }
                    await vm.loadGraph(accessToken: token)
                }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.body.weight(.semibold))
                    .rotationEffect(.degrees(vm.isLoading ? 360 : 0))
                    .animation(vm.isLoading ? .linear(duration: 0.8).repeatForever(autoreverses: false) : .default, value: vm.isLoading)
            }
            .buttonStyle(LiquidSecondaryButtonStyle())
            .disabled(vm.isLoading)
        }
    }

    private func graphStatBadge(_ value: String, label: String, icon: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(.subheadline, design: .rounded).weight(.bold))
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.white.opacity(0.16))
        .clipShape(Capsule())
    }

    // MARK: - Filter Chips

    private var filterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(filterTypes, id: \.0) { label, type in
                    Button {
                        withAnimation(.spring(response: 0.28, dampingFraction: 0.8)) {
                            vm.filterType = type
                        }
                        Task {
                            guard let token = session.accessToken else { return }
                            await vm.loadGraph(accessToken: token)
                        }
                    } label: {
                        Text(label)
                            .font(.subheadline.weight(.bold))
                            .minimumScaleFactor(0.85)
                            .foregroundStyle(vm.filterType == type ? .white : .primary)
                            .padding(.horizontal, 18)
                            .padding(.vertical, 10)
                            .background {
                                if vm.filterType == type {
                                    Capsule()
                                        .fill(
                                            LinearGradient(
                                                colors: [Color(red: 0.10, green: 0.53, blue: 0.95), Color(red: 0.03, green: 0.70, blue: 0.78)],
                                                startPoint: .leading,
                                                endPoint: .trailing
                                            )
                                        )
                                        .matchedGeometryEffect(id: "filter-pill", in: filterNamespace)
                                } else {
                                    Capsule()
                                        .fill(Color.white.opacity(0.18))
                                }
                            }
                            .overlay(Capsule().stroke(Color.white.opacity(0.24), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
        .padding(.vertical, 6)
    }

    // MARK: - Graph Canvas

    private var graphCanvas: some View {
        GeometryReader { geo in
            ZStack {
                RoundedRectangle(cornerRadius: 26, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.16),
                                Color(red: 0.75, green: 0.90, blue: 0.97).opacity(0.18)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .overlay {
                        gridPattern
                            .opacity(0.14)
                            .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
                    }

                // Loading
                if vm.isLoading {
                    VStack(spacing: 12) {
                        ProgressView()
                            .scaleEffect(1.2)
                        Text("Building your idea graph...")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                // Error
                if let error = vm.errorMessage {
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.title2)
                            .foregroundStyle(.red)
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
                }

                // Empty state
                if !vm.isLoading && vm.errorMessage == nil && vm.nodes.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "sparkles")
                            .font(.system(size: 44))
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [.blue, .purple],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                        Text("No entities yet")
                            .font(.headline)
                        Text("Record conversations and the AI will extract people, projects, and topics automatically.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 40)
                    }
                }

                // Graph
                if !vm.nodes.isEmpty {
                    let canvasSize = CGSize(
                        width: max(700, geo.size.width * 1.35),
                        height: max(700, geo.size.height * 1.25)
                    )
                    let offsetX = (geo.size.width - canvasSize.width * graphScale) / 2
                    let offsetY = (geo.size.height - canvasSize.height * graphScale) / 2

                    ZStack {
                        // Connection lines
                        if let graph = vm.graphData {
                            ForEach(graph.edges) { edge in
                                edgeLine(edge: edge)
                            }
                        }

                        // Entity nodes
                        ForEach(vm.nodes) { node in
                            entityNode(node)
                                .position(node.position)
                        }
                    }
                    .frame(width: canvasSize.width, height: canvasSize.height)
                    .scaleEffect(viewportScale)
                    .offset(
                        x: offsetX + viewportOffset.width,
                        y: offsetY + viewportOffset.height
                    )
                    .contentShape(Rectangle())
                    .highPriorityGesture(panGesture)
                    .simultaneousGesture(zoomGesture)
                    .onTapGesture(count: 2) {
                        resetViewport(animated: true)
                    }
                    .onChange(of: vm.filterType) { _, _ in
                        resetViewport(animated: true)
                    }
                    .onChange(of: vm.nodes.count) { _, _ in
                        resetViewport(animated: true)
                    }
                }

                if !vm.nodes.isEmpty {
                    VStack {
                        Spacer()
                        HStack {
                            Label("Pinch to zoom, drag to explore", systemImage: "hand.draw")
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(Color.white.opacity(0.18))
                                .clipShape(Capsule())
                            Spacer()
                        }
                        .padding(12)
                    }
                    .allowsHitTesting(false)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minHeight: 420)
        .liquidCard()
        .padding(.horizontal, 16)
    }

    // MARK: - Edge Line

    @ViewBuilder
    private func edgeLine(edge: IdeaGraphConnection) -> some View {
        let sourceNode = vm.nodes.first { $0.entity.id == edge.source_entity_id }
        let targetNode = vm.nodes.first { $0.entity.id == edge.target_entity_id }

        if let src = sourceNode, let tgt = targetNode {
            let isRelatedToSelection: Bool = {
                guard let selected = vm.selectedNode else { return true }
                return selected.entity.id == edge.source_entity_id || selected.entity.id == edge.target_entity_id
            }()
            let lineWidth = max(1.0, min(CGFloat(edge.shared_session_count) * 1.5, 5.0))
            let baseOpacity = min(0.15 + Double(edge.shared_session_count) * 0.1, 0.55)
            let opacity = isRelatedToSelection ? baseOpacity : 0.07
            let mid = CGPoint(
                x: (src.position.x + tgt.position.x) / 2,
                y: (src.position.y + tgt.position.y) / 2
            )
            let bend: CGFloat = CGFloat((edge.id.hashValue % 13) - 6) * 4.0
            let control = CGPoint(x: mid.x + bend, y: mid.y - bend)

            Path { path in
                path.move(to: src.position)
                path.addQuadCurve(to: tgt.position, control: control)
            }
            .stroke(
                LinearGradient(
                    colors: [
                        Color.entityColor(for: src.entity.entity_type).opacity(opacity),
                        Color.entityColor(for: tgt.entity.entity_type).opacity(opacity),
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                ),
                lineWidth: lineWidth
            )
            .animation(.easeInOut(duration: 0.25), value: vm.selectedNode?.id)
        }
    }

    // MARK: - Entity Node

    private func entityNode(_ node: GraphNodePosition) -> some View {
        let isSelected = vm.selectedNode?.id == node.id
        let color = Color.entityColor(for: node.entity.entity_type)

        return Button {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.7)) {
                vm.selectNode(isSelected ? nil : node)
            }
            if !isSelected, let token = session.accessToken {
                Task {
                    await vm.loadMentions(entityID: node.entity.id, accessToken: token)
                }
            }
        } label: {
            ZStack {
                // Outer glow
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [color.opacity(0.4), color.opacity(0.0)],
                            center: .center,
                            startRadius: node.radius * 0.3,
                            endRadius: node.radius * 1.6
                        )
                    )
                    .frame(width: node.radius * 3, height: node.radius * 3)

                // Main bubble
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [color.opacity(0.9), color.opacity(0.5)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: node.radius * 2, height: node.radius * 2)
                    .overlay(
                        Circle()
                            .stroke(isSelected ? Color.white : color.opacity(0.6), lineWidth: isSelected ? 3 : 1.5)
                    )
                    .shadow(color: color.opacity(0.35), radius: 8, x: 0, y: 4)

                // Icon + Name
                VStack(spacing: 2) {
                    Image(systemName: node.entity.typeIcon)
                        .font(.system(size: max(10, node.radius * 0.4)))
                        .foregroundStyle(.white)
                    Text(node.entity.name)
                        .font(.system(size: max(8, node.radius * 0.3), weight: .semibold, design: .rounded))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                        .frame(maxWidth: node.radius * 2 - 8)
                }
            }
        }
        .buttonStyle(.plain)
        .scaleEffect(isSelected ? 1.15 : 1.0)
        .animation(.spring(response: 0.3, dampingFraction: 0.65), value: isSelected)
    }

    // MARK: - Entity Detail Panel

    private func entityDetailPanel(_ node: GraphNodePosition) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: node.entity.typeIcon)
                    .foregroundStyle(Color.entityColor(for: node.entity.entity_type))
                    .font(.title3)
                VStack(alignment: .leading, spacing: 1) {
                    Text(node.entity.name)
                        .font(.system(.headline, design: .rounded))
                    Text(node.entity.entity_type.capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                VStack(alignment: .trailing) {
                    Text("\(node.entity.mention_count)")
                        .font(.system(.title3, design: .rounded).weight(.bold))
                    Text("mentions")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Button {
                    withAnimation(.spring(response: 0.28, dampingFraction: 0.88)) {
                        vm.selectNode(nil)
                    }
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.bold())
                        .frame(width: 26, height: 26)
                        .background(Color.white.opacity(0.14))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }

            if vm.mentionsLoading {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
            } else if !vm.mentions.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(vm.mentions) { mention in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 4) {
                                    Image(systemName: "waveform")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    Text(mention.created_at.formatted(date: .abbreviated, time: .shortened))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                if let snippet = mention.context_snippet, !snippet.isEmpty {
                                    Text(snippet)
                                        .font(.caption)
                                        .foregroundStyle(.primary)
                                        .lineLimit(3)
                                }
                                if let confidence = mention.confidence {
                                    HStack(spacing: 4) {
                                        Image(systemName: "gauge.with.dots.needle.33percent")
                                            .font(.caption2)
                                        Text(String(format: "%.0f%%", confidence * 100))
                                            .font(.caption2)
                                    }
                                    .foregroundStyle(.secondary)
                                }
                            }
                            .padding(10)
                            .frame(width: 200)
                            .background(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .fill(Color.white.opacity(0.08))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .stroke(Color.white.opacity(0.15), lineWidth: 1)
                            )
                        }
                    }
                }
            } else {
                Text("No mentions loaded yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(14)
        .liquidCard()
        .padding(.horizontal, 16)
        .padding(.bottom, 10)
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    private var graphScale: CGFloat {
        viewportScale
    }

    private var panGesture: some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { value in
                viewportOffset = CGSize(
                    width: committedOffset.width + value.translation.width,
                    height: committedOffset.height + value.translation.height
                )
            }
            .onEnded { _ in
                committedOffset = viewportOffset
            }
    }

    private var zoomGesture: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                viewportScale = min(max(committedScale * value, 0.55), 2.8)
            }
            .onEnded { _ in
                committedScale = viewportScale
            }
    }

    private var gridPattern: some View {
        Canvas { context, size in
            let step: CGFloat = 26
            var path = Path()

            stride(from: 0, through: size.width, by: step).forEach { x in
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
            }
            stride(from: 0, through: size.height, by: step).forEach { y in
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
            }

            context.stroke(path, with: .color(.white.opacity(0.14)), lineWidth: 0.5)
        }
    }

    private func resetViewport(animated: Bool) {
        let updates = {
            viewportOffset = .zero
            committedOffset = .zero
            viewportScale = 1.0
            committedScale = 1.0
        }
        if animated {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
                updates()
            }
        } else {
            updates()
        }
    }
}
