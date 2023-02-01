from gfs_dynamical_core import (
    get_default_state, GFSDynamicalCore, get_grid
)
import random
from sympl import (
    TendencyComponent, DiagnosticComponent, Stepper,
    ImplicitTendencyComponent, TendencyStepper, TimeDifferencingWrapper
)
import numpy as np
import pytest
import unittest
from datetime import timedelta


def call_component(component, state):
    if isinstance(component, (DiagnosticComponent, TendencyComponent)):
        return component(state)
    elif isinstance(component, (Stepper, ImplicitTendencyComponent, TendencyStepper)):
        return component(state, timedelta(hours=1))
    else:
        raise AssertionError('Component is of unknown type')


class GetGridTests(unittest.TestCase):

    def assert_grid_quantities_present(self, state, latitude=False, longitude=False):
        grid_names = ['time', 'air_pressure', 'air_pressure_on_interface_levels',
                      'surface_air_pressure', 'height_on_ice_interface_levels']
        if latitude:
            grid_names.append('latitude')
        if longitude:
            grid_names.append('longitude')
        for name in grid_names:
            if name not in state:
                raise AssertionError(
                    'Grid quantity {} is not present in state_array.'.format(name))

    def assert_grid_quantities_have_dimensions(self, state, dim_names):
        state_dim_names = []
        for name, value in state.items():
            if name != 'time':
                state_dim_names.extend(value.dims)
        extra_dims = set(state_dim_names).difference(dim_names)
        missing_dims = set(dim_names).difference(state_dim_names)
        assert len(extra_dims) == 0
        assert len(missing_dims) == 0

    def assert_grid_dimensions_have_lengths(self, state, dim_lengths):
        state_dim_lengths = {}
        for name, value in state.items():
            if name != 'time':
                for dim_name, length in zip(value.dims, value.shape):
                    if dim_name not in state_dim_lengths:
                        state_dim_lengths[dim_name] = length
                    elif state_dim_lengths[dim_name] != length:
                        print(
                            {name: zip(value.dims, value.shape)
                             for name, value in state.items()
                             if name != 'time'})
                        raise AssertionError(
                            'Inconsistent lengths {} and {} for dimension {}'.format(
                                length, state_dim_lengths[dim_name], dim_name))
        for dim_name, length in dim_lengths.items():
            if state_dim_lengths[dim_name] != length:
                raise AssertionError(
                    'Want length {} for dimension {} but instead have '
                    'length {}'.format(
                        length, dim_name, state_dim_lengths[dim_name])
                )

    def test_get_default_grid(self):
        grid = get_grid()
        self.assert_grid_quantities_present(grid)
        self.assert_grid_quantities_have_dimensions(
            grid, ['lat', 'lon', 'mid_levels', 'interface_levels', 'ice_interface_levels'])

    def test_get_1d_vertical_grid(self):
        grid = get_grid(nz=20)
        self.assert_grid_quantities_present(grid)
        self.assert_grid_quantities_have_dimensions(
            grid, ['lat', 'lon', 'mid_levels', 'interface_levels', 'ice_interface_levels'])
        self.assert_grid_dimensions_have_lengths(
            grid, {'mid_levels': 20, 'interface_levels': 21}
        )

    def test_get_3d_grid(self):
        grid = get_grid(nx=4, ny=6, nz=20)
        self.assert_grid_quantities_present(grid, latitude=True, longitude=True)
        self.assert_grid_quantities_have_dimensions(
            grid, ['mid_levels', 'interface_levels', 'lat', 'lon', 'ice_interface_levels'])
        self.assert_grid_dimensions_have_lengths(
            grid, {'mid_levels': 20, 'interface_levels': 21, 'lat': 6, 'lon': 4}
        )

    def test_get_3d_grid_custom_dim_names(self):
        grid = get_grid(nx=3, ny=8, nz=20, x_name='name1', y_name='name2')
        self.assert_grid_quantities_present(grid, latitude=True, longitude=True)
        self.assert_grid_quantities_have_dimensions(
            grid, ['mid_levels', 'interface_levels', 'name1', 'name2', 'ice_interface_levels'])
        self.assert_grid_dimensions_have_lengths(
            grid, {'mid_levels': 20, 'interface_levels': 21, 'name1': 3, 'name2': 8}
        )

    def test_get_1d_grid_custom_surface_pressure(self):
        grid = get_grid(nz=20, p_surf_in_Pa=0.9e5)
        self.assert_grid_quantities_present(grid)
        self.assert_grid_quantities_have_dimensions(
            grid, ['lat', 'lon', 'mid_levels', 'interface_levels', 'ice_interface_levels'])
        self.assert_grid_dimensions_have_lengths(
            grid, {'mid_levels': 20, 'interface_levels': 21}
        )
        p = grid['air_pressure'].to_units('Pa')
        p_interface = grid['air_pressure_on_interface_levels'].to_units('Pa')
        assert grid['surface_air_pressure'].to_units('Pa') == 0.9e5
        assert np.isclose(p_interface[0], 0.9e5)
        assert np.all(p_interface[1:].values < p_interface[:-1].values)
        assert np.all(p[1:].values < p[:-1].values)
        assert np.all(p[:].values < p_interface[:-1].values)
        assert np.all(p[:].values > p_interface[1:].values)


def assert_state_is_full(state, component):
    for dict_name in ('output_properties', 'tendency_properties', 'diagnostic_proprerties'):
        if hasattr(component, dict_name):
            for quantity_name, properties in getattr(component, dict_name).items():
                if quantity_name not in component.input_properties.keys():
                    continue
                elif 'dims' in properties.keys():
                    dims = properties['dims']
                else:
                    dims = component.input_properties[quantity_name]['dims']
                missing_dims = set(dims).difference(
                    ['*'] + list(state[quantity_name].dims))
                assert len(missing_dims) == 0, '{} is missing {} dims {}'.format(
                    quantity_name, dict_name, missing_dims)


def create_default_test_for(cls):
    def test_component(self):
        component = cls()
        state = get_default_state([component])
        call_component(component, state)
    test_component.__name__ = 'test_{}'.format(cls.__name__)
    return test_component


def create_1d_grid_test_for(cls):
    def test_component_1d_grid(self):
        grid = get_grid(nz=10)
        component = cls()
        state = get_default_state([component], grid_state=grid)
        assert_state_is_full(state, component)
        call_component(component, state)
    test_component_1d_grid.__name__ = 'test_{}_1d_grid'.format(cls.__name__)
    return test_component_1d_grid


def create_2d_grid_test_for(cls):
    def test_component_2d_grid(self):
        grid = get_grid(nx=3, nz=10)
        component = cls()
        state = get_default_state([component], grid_state=grid)
        assert_state_is_full(state, component)
        call_component(component, state)
    test_component_2d_grid.__name__ = 'test_{}_2d_grid'.format(cls.__name__)
    return test_component_2d_grid


def create_3d_grid_test_for(cls):
    def test_component_3d_grid(self):
        grid = get_grid(nx=3, ny=4, nz=10)
        component = cls()
        state = get_default_state([component], grid_state=grid)
        assert_state_is_full(state, component)
        call_component(component, state)
    test_component_3d_grid.__name__ = 'test_{}_3d_grid'.format(cls.__name__)
    return test_component_3d_grid


# class TestGFSDycoreWith32VerticalLevels(unittest.TestCase):

#     def get_component_instance(self):
#         return GFSDynamicalCore()

#     def test_component_3d_grid(self):
#         grid = get_grid(nx=16, ny=16, nz=32)
#         component = self.get_component_instance()
#         state = get_default_state([component], grid_state=grid)
#         call_component(component, state)

### enable this back up later! disabling to test build

if __name__ == '__main__':
    pytest.main([__file__])
