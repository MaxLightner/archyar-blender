"""Semantic MEP routes and wall-hosted tube luminaires for Archyar Blender.

The generated meshes are implementation details; only the empty controllers
carry editable architectural dimensions and stable identity.
"""
import json
import math
import uuid

import bpy
from bpy.props import EnumProperty, FloatProperty
from mathutils import Vector

from . import geometry


def route_mesh(points, width, depth, service):
    """Create one continuous watertight polyline solid with mitered elbows."""
    if len(points) < 2 or len(points) > 128:
        raise ValueError("Route requires 2–128 points")
    if not .008 <= width <= 3.0:
        raise ValueError("Route width outside permitted range")
    if service == 'DUCT' and not .04 <= depth <= 3.0:
        raise ValueError("Duct section height outside permitted range")
    if service not in {'DUCT', 'PIPE', 'CONDUIT'}:
        raise ValueError("Unknown service type")
    segments = []
    for a, b in zip(points, points[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        span = math.hypot(dx, dy)
        if span < .05:
            raise ValueError("Route segment must be at least 5 cm")
        segments.append((dx/span, dy/span))
    ring_sides = 4 if service == 'DUCT' else 12
    height = depth if service == 'DUCT' else width
    verts = []
    for i, (px, py, pz) in enumerate(points):
        before = segments[max(0, i-1)]
        after = segments[min(len(segments)-1, i)]
        nb = Vector((-before[1], before[0]))
        na = Vector((-after[1], after[0]))
        normal = nb + na
        if normal.length < .05:
            raise ValueError("180-degree reversal is not a valid elbow")
        normal.normalize()
        denom = max(.34, normal.dot(na))
        factor = min(2.9, 1.0/denom)
        if service == 'DUCT':
            offsets = [(1,-1),(-1,-1),(-1,1),(1,1)]
        else:
            offsets = [(math.cos(2*math.pi*j/ring_sides),
                        math.sin(2*math.pi*j/ring_sides))
                       for j in range(ring_sides)]
        for sx, sz in offsets:
            sideways = sx*width*.5*factor
            verts.append((px+normal.x*sideways, py+normal.y*sideways,
                          pz+sz*height*.5))
    faces = [tuple(reversed(tuple(range(ring_sides)))),
             tuple((len(points)-1)*ring_sides+j for j in range(ring_sides))]
    for station in range(len(points)-1):
        a=station*ring_sides;b=(station+1)*ring_sides
        for j in range(ring_sides):
            k=(j+1)%ring_sides
            faces.append((a+j,a+k,b+k,b+j))
    return verts, faces


def rebuild_route(root, points=None):
    service=root.get('archyar_service', 'DUCT')
    width=float(root.get('archyar_width', .4))
    depth=float(root.get('archyar_height', .25))
    if points is None:
        points=json.loads(root['archyar_points'])
    verts,faces=route_mesh(points,width,depth,service)
    visual=next((c for c in root.children if c.get('archyar_route_visual')),None)
    if visual is None:
        visual=geometry.mesh_object("Archyar | Generated MEP Surface",verts,faces,
            geometry.material('Duct galvanized metal',(.52,.62,.67)) if service=='DUCT'
            else geometry.material('Pipe service',(.45,.72,.81)),parent=root)
        visual['archyar_route_visual']=True
    else:
        visual.data.clear_geometry()
        visual.data.from_pydata(verts,[],faces)
        visual.data.update()


def create_route(points, service, width, depth):
    if not points or len(points)<2:
        raise ValueError('Complete a route before placing')
    root=geometry.empty("Archyar | "+service+" Route")
    root['archyar_kind']='MEP_ROUTE'
    root['archyar_id']=str(uuid.uuid4())
    root['archyar_service']=service
    root['archyar_width']=float(width)
    root['archyar_height']=float(depth)
    root['archyar_points']=json.dumps(points)
    root.lock_location=(True,True,True)
    root.lock_rotation=(True,True,True)
    root.lock_scale=(True,True,True)
    rebuild_route(root)
    geometry.select(root)
    return root


def rebuild_wall_light(root):
    wall=root.parent
    if wall is None or wall.get('archyar_kind')!='WALL':
        raise ValueError('A wall-mounted luminaire requires a host wall')
    span=geometry.length(wall.archyar_wall.start,wall.archyar_wall.end)
    width=float(root.get('archyar_width',1.2))
    height=float(root.get('archyar_height',.075))
    t=float(root.get('archyar_t',.5))
    base=float(root.get('archyar_mount_height',2.15))
    side=1 if int(root.get('archyar_side',1))>=0 else -1
    if not (.15<=width<=span-.10 and .02<=height<=.4 and
            width/(2*span)+.01<=t<=1-width/(2*span)-.01 and
            height/2<=base<=wall.archyar_wall.height-height/2):
        raise ValueError('Light must fit entirely inside its hosting wall')
    root.location=((t-.5)*span, side*(wall.archyar_wall.thickness*.5+.038),
                   base-wall.archyar_wall.height*.5)
    visual=next((c for c in root.children if c.get('archyar_light_visual')),None)
    if visual is None:
        visual=geometry.box('Archyar | Wall Tube Light (generated)',root,
                            (0,0,0),(width,.055,height),
                            geometry.material('Tube light diffuser',(.95,.97,.91)))
        visual['archyar_light_visual']=True
    else:
        visual.data.clear_geometry()
        visual.data.from_pydata(geometry.box_vertices(width,.055,height),
                                [],geometry._BOX_FACES)
        visual.data.update()


def create_wall_light(wall):
    if wall is None or wall.get('archyar_kind')!='WALL':
        raise ValueError('Select an Archyar wall for the light')
    span=geometry.length(wall.archyar_wall.start,wall.archyar_wall.end)
    if span<.28:
        raise ValueError('Wall is too short for a light')
    root=geometry.empty('Archyar | Wall Tube Light',parent=wall)
    root['archyar_kind']='WALL_LIGHT'
    root['archyar_id']=str(uuid.uuid4())
    root['archyar_width']=min(1.2,span-.12)
    root['archyar_height']=.075
    root['archyar_mount_height']=min(2.15,wall.archyar_wall.height-.08)
    root['archyar_t']=.5
    root['archyar_side']=1
    root.lock_location=(True,True,True)
    root.lock_rotation=(True,True,True)
    root.lock_scale=(True,True,True)
    rebuild_wall_light(root)
    geometry.select(root)
    return root


def _constrain_angle(points, new_point, mode):
    if len(points)<2 or mode=='FREE':
        return new_point
    prev=Vector(points[-1][:2])-Vector(points[-2][:2])
    proposed=Vector(new_point[:2])-Vector(points[-1][:2])
    distance=proposed.length
    if prev.length<.05 or distance<.05:
        return new_point
    step=math.radians(45 if mode=='45' else 90)
    desired=math.atan2(proposed.y,proposed.x)
    heading=math.atan2(prev.y,prev.x)
    snapped=heading+round((desired-heading)/step)*step
    return (points[-1][0]+math.cos(snapped)*distance,
            points[-1][1]+math.sin(snapped)*distance,new_point[2])


class ARCHYAR_OT_draw_mep(bpy.types.Operator):
    bl_idname='archyar.draw_mep'
    bl_label='Draw MEP Route'
    bl_description='Click route corners; Enter/right-click finishes; Esc cancels'
    bl_options={'REGISTER','UNDO','BLOCKING'}

    def invoke(self,context,event):
        from .operators import _metres_ok, _window_region
        try:
            _metres_ok(context)
            _window_region(context)
        except ValueError as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        self.points=[]
        self.ghost=None
        context.window_manager.modal_handler_add(self)
        context.scene.archyar_active_tool='MEP'
        self.report({'INFO'},'Click corners, Enter to finish; Esc to cancel')
        return {'RUNNING_MODAL'}

    def _destroy_ghost(self):
        if self.ghost and self.ghost.name in bpy.data.objects:
            geometry.remove_tree(self.ghost)
        self.ghost=None

    def _preview(self,context,point):
        points=self.points+([point] if point else [])
        if len(points)<2:
            return
        scene=context.scene
        try:
            verts,faces=route_mesh(points,scene.archyar_mep_width,
                        scene.archyar_mep_height,scene.archyar_mep_kind)
        except ValueError:
            return
        if self.ghost is None:
            self.ghost=geometry.empty('Archyar | MEP Preview')
            self.ghost['archyar_preview']=True
            ob=geometry.mesh_object('Archyar | MEP Ghost',verts,faces,
                geometry.material('MEP Preview',(.82,.65,.38)),parent=self.ghost)
            ob['archyar_route_visual']=True
            geometry.mark_preview(self.ghost,True)
        else:
            visual=next(c for c in self.ghost.children if c.get('archyar_route_visual'))
            visual.data.clear_geometry()
            visual.data.from_pydata(verts,[],faces)
            visual.data.update()
        context.area.tag_redraw()

    def modal(self,context,event):
        scene=context.scene
        if event.type=='ESC':
            self._destroy_ghost()
            scene.archyar_active_tool=''
            return {'CANCELLED'}
        if event.type in {'RET','NUMPAD_ENTER','RIGHTMOUSE'} and event.value=='PRESS':
            self._destroy_ghost()
            scene.archyar_active_tool=''
            if len(self.points)<2:
                return {'CANCELLED'}
            try:
                create_route(self.points,scene.archyar_mep_kind,
                             scene.archyar_mep_width,scene.archyar_mep_height)
            except ValueError as exc:
                self.report({'ERROR'},str(exc))
                return {'CANCELLED'}
            return {'FINISHED'}
        if event.type in {'MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type not in {'MOUSEMOVE','LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        from .operators import ground_point, snap_point
        p=ground_point(context,event)
        if p is None:
            return {'PASS_THROUGH'}
        xy=snap_point(p,scene)
        new_point=(float(xy.x),float(xy.y),float(scene.archyar_mep_elevation))
        new_point=_constrain_angle(self.points,new_point,scene.archyar_mep_angle)
        if event.type=='MOUSEMOVE':
            self._preview(context,new_point)
            return {'RUNNING_MODAL'}
        if event.value=='PRESS':
            if not self.points or math.dist(self.points[-1],new_point)>=.05:
                self.points.append(new_point)
                self._preview(context,None)
        return {'RUNNING_MODAL'}


class ARCHYAR_OT_apply_mep(bpy.types.Operator):
    bl_idname='archyar.apply_mep'
    bl_label='Apply MEP Dimensions'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        obj=context.active_object
        if obj is None or obj.get('archyar_kind')!='MEP_ROUTE':
            return {'CANCELLED'}
        try:
            rebuild_route(obj)
        except (ValueError,KeyError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ARCHYAR_OT_wall_light(bpy.types.Operator):
    bl_idname='archyar.wall_light'
    bl_label='Place Wall Tube Light'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        root=context.active_object
        if root is not None and root.get('archyar_kind')=='WALL_LIGHT':
            root=root.parent
        try:
            create_wall_light(root)
        except ValueError as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ARCHYAR_OT_apply_wall_light(bpy.types.Operator):
    bl_idname='archyar.apply_wall_light'
    bl_label='Apply Wall Tube Light'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        root=context.active_object
        if root is None or root.get('archyar_kind')!='WALL_LIGHT':
            return {'CANCELLED'}
        try:
            rebuild_wall_light(root)
        except ValueError as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


def draw_inspector(layout,root):
    if root.get('archyar_kind')=='MEP_ROUTE':
        layout.label(text='MEP route | non-destructive controller')
        layout.label(text='Service: '+str(root.get('archyar_service')))
        layout.prop(root,'["archyar_width"]',text='Width / diameter (m)')
        if root.get('archyar_service')=='DUCT':
            layout.prop(root,'["archyar_height"]',text='Section height (m)')
        layout.operator('archyar.apply_mep',icon='CHECKMARK')
        layout.label(text='Bends: '+str(max(0,len(json.loads(root['archyar_points']))-2)))
    elif root.get('archyar_kind')=='WALL_LIGHT':
        layout.label(text='Wall-mounted tube luminaire')
        layout.prop(root,'["archyar_width"]',text='Length (m)')
        layout.prop(root,'["archyar_height"]',text='Height (m)')
        layout.prop(root,'["archyar_mount_height"]',text='Center above floor (m)')
        layout.prop(root,'["archyar_t"]',text='Fraction along wall')
        layout.prop(root,'["archyar_side"]',text='Wall side (+/-)')
        layout.operator('archyar.apply_wall_light',icon='CHECKMARK')
        layout.label(text='Host wall is mandatory; transforms are locked')


CLASSES=(ARCHYAR_OT_draw_mep,ARCHYAR_OT_apply_mep,
         ARCHYAR_OT_wall_light,ARCHYAR_OT_apply_wall_light)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.archyar_mep_kind=EnumProperty(name='Route Type',items=[
        ('DUCT','Rectangular air duct','Duct with a rectangular solid section'),
        ('PIPE','Pipe','Circular pipe'),
        ('CONDUIT','Electrical conduit','Circular conduit')])
    bpy.types.Scene.archyar_mep_width=FloatProperty(name='Width / Diameter',default=.4,min=.008,max=3,unit='LENGTH')
    bpy.types.Scene.archyar_mep_height=FloatProperty(name='Duct Section Height',default=.25,min=.04,max=3,unit='LENGTH')
    bpy.types.Scene.archyar_mep_elevation=FloatProperty(name='Center Height (Z)',default=2.65,min=-10,max=30,unit='LENGTH')
    bpy.types.Scene.archyar_mep_angle=EnumProperty(name='Turn Snap',items=[
        ('FREE','Free','No angular snapping'),('45','45°','45-degree increments'),('90','90°','90-degree increments')])


def unregister():
    for attr in ('archyar_mep_kind','archyar_mep_width','archyar_mep_height',
                 'archyar_mep_elevation','archyar_mep_angle'):
        delattr(bpy.types.Scene,attr)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
